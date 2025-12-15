"""
Uses Spark and geospatial clustering algorithms (DBSCAN, K-Means) to identify:
1. Geographic hotspots of disease outbreaks
2. Spatially-clustered symptom patterns
3. Borough-level and neighborhood-level disease clusters
4. Temporal evolution of spatial clusters
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

# PySpark
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.postgresql:postgresql:42.7.1 pyspark-shell'
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
if sys.version_info >= (3, 0):
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, count, collect_list, avg, min as spark_min, max as spark_max
from pyspark.sql.types import StructType, StructField, StringType, FloatType, IntegerType, TimestampType

# Clustering algorithms
from sklearn.cluster import DBSCAN, KMeans
from sklearn.preprocessing import StandardScaler

# Database clients
import psycopg2
import chromadb

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SpatialClusteringAnalyzer:
    """
    Spatial clustering analyzer for disease surveillance data
    """

    def __init__(
        self,
        # Spark config
        spark_app_name: str = "NYC_Disease_Spatial_Clustering",
        spark_memory: str = "4g",
        
        # TimescaleDB config
        postgres_host: str = "localhost",
        postgres_port: int = 5432,
        postgres_db: str = "nyc_disease_surveillance",
        postgres_user: str = "postgres",
        postgres_password: str = "postgres",
        
        # ChromaDB config
        chromadb_path: str = "data/chromadb",
        chromadb_collection: str = "nyc_disease_surveillance",
        
        # Output config
        output_dir: str = "data/spatial_clusters"
    ):
        """
        Initialize spatial clustering analyzer

        Args:
            spark_app_name: Spark application name
            spark_memory: Spark memory allocation
            postgres_*: TimescaleDB connection parameters
            chromadb_*: ChromaDB connection parameters
            output_dir: Directory for cluster analysis results
        """
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize Spark Session
        logger.info("Initializing Spark Session...")
        self.spark = SparkSession.builder \
            .appName(spark_app_name) \
            .master("local[*]") \
            .config("spark.driver.memory", spark_memory) \
            .config("spark.executor.memory", spark_memory) \
            .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
            .config("spark.jars.packages", "org.postgresql:postgresql:42.7.1") \
            .getOrCreate()

        self.spark.sparkContext.setLogLevel("WARN")

        # TimescaleDB connection
        self.postgres_config = {
            'host': postgres_host,
            'port': postgres_port,
            'database': postgres_db,
            'user': postgres_user,
            'password': postgres_password
        }

        # ChromaDB connection
        logger.info(f"Connecting to ChromaDB at: {chromadb_path}")
        self.chroma_client = chromadb.PersistentClient(path=chromadb_path)
        try:
            self.chroma_collection = self.chroma_client.get_collection(name=chromadb_collection)
            logger.info(f"ChromaDB collection '{chromadb_collection}' loaded: {self.chroma_collection.count()} documents")
        except:
            logger.warning(f"ChromaDB collection '{chromadb_collection}' not found. Semantic features disabled.")
            self.chroma_collection = None

        # NYC borough coordinates (for mapping)
        self.borough_coords = {
            "Manhattan": (40.7831, -73.9712),
            "Brooklyn": (40.6782, -73.9442),
            "Queens": (40.7282, -73.7949),
            "Bronx": (40.8448, -73.8648),
            "Staten Island": (40.5795, -74.1502)
        }

        logger.info("Spatial Clustering Analyzer initialized successfully")

    def load_data_from_timescaledb(
        self,
        time_window_days: Optional[int] = None,
        disease_filter: Optional[List[str]] = None,
        borough_filter: Optional[List[str]] = None
    ) -> DataFrame:
        """
        Load disease event data from TimescaleDB into Spark DataFrame

        Args:
            time_window_days: Filter to last N days (None = all data)
            disease_filter: List of diseases to include (None = all)
            borough_filter: List of boroughs to include (None = all)

        Returns:
            Spark DataFrame with disease events
        """
        logger.info("Loading data from TimescaleDB...")

        # Build SQL query
        query = """
            SELECT 
                id,
                timestamp,
                source,
                text_content,
                diseases,
                symptoms,
                severity,
                confidence,
                borough,
                neighborhood,
                location_source,
                extracted_locations,
                latitude,
                longitude
            FROM disease_events
            WHERE 1=1
        """

        # Add time filter
        if time_window_days:
            cutoff_date = (datetime.now() - timedelta(days=time_window_days)).strftime('%Y-%m-%d')
            query += f" AND timestamp >= '{cutoff_date}'"

        # Add disease filter
        if disease_filter:
            diseases_str = "', '".join(disease_filter)
            query += f" AND EXISTS (SELECT 1 FROM unnest(diseases) AS d WHERE d IN ('{diseases_str}'))"

        # Add borough filter
        if borough_filter:
            boroughs_str = "', '".join(borough_filter)
            query += f" AND borough IN ('{boroughs_str}')"

        # Add location filter (only records with borough/neighborhood)
        query += " AND (borough IS NOT NULL OR neighborhood IS NOT NULL)"

        query += " ORDER BY timestamp DESC"

        # JDBC connection URL
        jdbc_url = f"jdbc:postgresql://{self.postgres_config['host']}:{self.postgres_config['port']}/{self.postgres_config['database']}"

        # Load into Spark DataFrame
        df = self.spark.read \
            .format("jdbc") \
            .option("url", jdbc_url) \
            .option("query", query) \
            .option("user", self.postgres_config['user']) \
            .option("password", self.postgres_config['password']) \
            .option("driver", "org.postgresql.Driver") \
            .load()

        record_count = df.count()
        logger.info(f"Loaded {record_count} records from TimescaleDB")

        if record_count == 0:
            logger.warning("No records found matching filters!")

        return df

    def prepare_spatial_features(self, df: DataFrame) -> pd.DataFrame:
        """
        Prepare spatial features for clustering

        Args:
            df: Spark DataFrame with disease events

        Returns:
            Pandas DataFrame with spatial features
        """
        logger.info("Preparing spatial features...")

        # Convert to Pandas for scikit-learn
        pdf = df.toPandas()

        # Use actual latitude/longitude if available, otherwise map from borough
        pdf['lat'] = pdf.apply(
            lambda row: row['latitude'] if pd.notna(row.get('latitude')) 
            else (self.borough_coords.get(row['borough'], (None, None))[0] if row.get('borough') else None),
            axis=1
        )
        pdf['lon'] = pdf.apply(
            lambda row: row['longitude'] if pd.notna(row.get('longitude'))
            else (self.borough_coords.get(row['borough'], (None, None))[1] if row.get('borough') else None),
            axis=1
        )

        # Add jitter for neighborhood-level variation (only if no actual lat/lon)
        # This prevents all records in same borough from having identical coordinates
        np.random.seed(42)
        pdf['lat'] = pdf.apply(
            lambda row: row['lat'] + np.random.uniform(-0.02, 0.02) 
            if pd.notna(row['lat']) and pd.isna(row.get('latitude')) and pd.notna(row['neighborhood']) 
            else row['lat'],
            axis=1
        )
        pdf['lon'] = pdf.apply(
            lambda row: row['lon'] + np.random.uniform(-0.02, 0.02) 
            if pd.notna(row['lon']) and pd.isna(row.get('longitude')) and pd.notna(row['neighborhood']) 
            else row['lon'],
            axis=1
        )

        # Filter out records without coordinates
        pdf = pdf.dropna(subset=['lat', 'lon'])

        logger.info(f"Prepared {len(pdf)} records with spatial features")

        return pdf

    def dbscan_clustering(
        self,
        pdf: pd.DataFrame,
        eps_km: float = 2.0,
        min_samples: int = 5
    ) -> pd.DataFrame:
        """
        Perform DBSCAN spatial clustering

        Args:
            pdf: Pandas DataFrame with lat/lon
            eps_km: Maximum distance between points in km (epsilon parameter)
            min_samples: Minimum cluster size

        Returns:
            DataFrame with cluster labels
        """
        logger.info(f"Running DBSCAN clustering (eps={eps_km}km, min_samples={min_samples})...")

        # Extract coordinates
        coords = pdf[['lat', 'lon']].values

        # Convert eps from km to degrees (approximate: 1 degree ≈ 111 km)
        eps_degrees = eps_km / 111.0

        # Run DBSCAN
        dbscan = DBSCAN(eps=eps_degrees, min_samples=min_samples, metric='euclidean')
        pdf['cluster_id'] = dbscan.fit_predict(coords)

        # Statistics
        n_clusters = len(set(pdf['cluster_id'])) - (1 if -1 in pdf['cluster_id'] else 0)
        n_noise = list(pdf['cluster_id']).count(-1)

        logger.info(f"DBSCAN found {n_clusters} clusters, {n_noise} noise points")

        return pdf

    def kmeans_clustering(
        self,
        pdf: pd.DataFrame,
        n_clusters: int = 5
    ) -> pd.DataFrame:
        """
        Perform K-Means spatial clustering

        Args:
            pdf: Pandas DataFrame with lat/lon
            n_clusters: Number of clusters

        Returns:
            DataFrame with cluster labels
        """
        logger.info(f"Running K-Means clustering (k={n_clusters})...")

        # Extract coordinates
        coords = pdf[['lat', 'lon']].values

        # Standardize coordinates
        scaler = StandardScaler()
        coords_scaled = scaler.fit_transform(coords)

        # Run K-Means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        pdf['kmeans_cluster'] = kmeans.fit_predict(coords_scaled)

        # Get cluster centers in original space
        cluster_centers = scaler.inverse_transform(kmeans.cluster_centers_)

        logger.info(f"K-Means created {n_clusters} clusters")
        logger.info("Cluster centers:")
        for i, center in enumerate(cluster_centers):
            logger.info(f"  Cluster {i}: lat={center[0]:.4f}, lon={center[1]:.4f}")

        return pdf

    def analyze_clusters(self, pdf: pd.DataFrame, cluster_col: str = 'cluster_id') -> Dict:
        """
        Analyze cluster characteristics

        Args:
            pdf: DataFrame with cluster labels
            cluster_col: Name of cluster column

        Returns:
            Dictionary with cluster analysis
        """
        logger.info(f"Analyzing clusters ({cluster_col})...")

        cluster_analysis = {}

        for cluster_id in sorted(pdf[cluster_col].unique()):
            if cluster_id == -1:  # Skip noise points in DBSCAN
                continue

            cluster_data = pdf[pdf[cluster_col] == cluster_id]

            # Geographic stats
            centroid_lat = cluster_data['lat'].mean()
            centroid_lon = cluster_data['lon'].mean()

            # Disease distribution
            all_diseases = []
            for diseases_arr in cluster_data['diseases']:
                if isinstance(diseases_arr, list):
                    all_diseases.extend(diseases_arr)
                elif isinstance(diseases_arr, str):
                    try:
                        diseases_list = json.loads(diseases_arr) if diseases_arr.startswith('[') else [diseases_arr]
                        all_diseases.extend(diseases_list)
                    except:
                        pass

            disease_counts = pd.Series(all_diseases).value_counts().to_dict() if all_diseases else {}

            # Symptom distribution
            all_symptoms = []
            for symptoms_arr in cluster_data['symptoms']:
                if isinstance(symptoms_arr, list):
                    all_symptoms.extend(symptoms_arr)
                elif isinstance(symptoms_arr, str):
                    try:
                        symptoms_list = json.loads(symptoms_arr) if symptoms_arr.startswith('[') else [symptoms_arr]
                        all_symptoms.extend(symptoms_list)
                    except:
                        pass

            symptom_counts = pd.Series(all_symptoms).value_counts().to_dict() if all_symptoms else {}

            # Severity distribution
            severity_counts = cluster_data['severity'].value_counts().to_dict()

            # Borough distribution
            borough_counts = cluster_data['borough'].value_counts().to_dict()

            # Neighborhood distribution
            neighborhood_counts = cluster_data['neighborhood'].value_counts().to_dict()

            # Time range
            time_range = {
                'start': cluster_data['timestamp'].min(),
                'end': cluster_data['timestamp'].max()
            }

            cluster_analysis[int(cluster_id)] = {
                'size': len(cluster_data),
                'centroid': {'lat': centroid_lat, 'lon': centroid_lon},
                'boroughs': borough_counts,
                'neighborhoods': neighborhood_counts,
                'diseases': disease_counts,
                'symptoms': symptom_counts,
                'severity': severity_counts,
                'time_range': time_range,
                'avg_confidence': float(cluster_data['confidence'].mean()) if 'confidence' in cluster_data else None
            }

        logger.info(f"Analyzed {len(cluster_analysis)} clusters")

        return cluster_analysis

    def enrich_with_semantic_similarity(
        self,
        pdf: pd.DataFrame,
        cluster_col: str = 'cluster_id'
    ) -> Dict:
        """
        Enrich clusters with semantic similarity scores from ChromaDB

        Args:
            pdf: DataFrame with clusters
            cluster_col: Cluster column name

        Returns:
            Dictionary with semantic coherence scores per cluster
        """
        if not self.chroma_collection:
            logger.warning("ChromaDB not available, skipping semantic enrichment")
            return {}

        logger.info("Enriching clusters with semantic similarity...")

        semantic_scores = {}

        for cluster_id in sorted(pdf[cluster_col].unique()):
            if cluster_id == -1:
                continue

            cluster_data = pdf[pdf[cluster_col] == cluster_id]
            cluster_ids = cluster_data['id'].tolist()
            
            # Deduplicate IDs (same event may appear multiple times)
            unique_cluster_ids = list(set(cluster_ids))

            try:
                # Get embeddings for cluster members from ChromaDB
                results = self.chroma_collection.get(
                    ids=[str(cid) for cid in unique_cluster_ids[:100]],  # Limit to 100 for performance
                    include=['embeddings']
                )

                if results and results.get('embeddings'):
                    embeddings = np.array(results['embeddings'])

                    # Calculate pairwise cosine similarities
                    similarities = 1 - cdist(embeddings, embeddings, metric='cosine')

                    # Get average similarity (excluding diagonal)
                    mask = np.ones(similarities.shape, dtype=bool)
                    np.fill_diagonal(mask, False)
                    avg_similarity = similarities[mask].mean()

                    semantic_scores[int(cluster_id)] = {
                        'avg_cosine_similarity': float(avg_similarity),
                        'semantic_coherence': 'high' if avg_similarity > 0.7 else 'medium' if avg_similarity > 0.5 else 'low',
                        'sample_size': len(embeddings)
                    }
                else:
                    semantic_scores[int(cluster_id)] = {
                        'avg_cosine_similarity': None,
                        'semantic_coherence': 'unknown',
                        'sample_size': 0
                    }

            except Exception as e:
                logger.warning(f"Error getting semantic similarity for cluster {cluster_id}: {e}")
                semantic_scores[int(cluster_id)] = {
                    'avg_cosine_similarity': None,
                    'semantic_coherence': 'error',
                    'sample_size': 0
                }

        logger.info(f"Computed semantic similarity for {len(semantic_scores)} clusters")

        return semantic_scores

    def save_results(
        self,
        pdf: pd.DataFrame,
        cluster_analysis: Dict,
        semantic_scores: Dict,
        algorithm: str
    ):
        """
        Save clustering results to files

        Args:
            pdf: DataFrame with cluster assignments
            cluster_analysis: Cluster characteristics
            semantic_scores: Semantic similarity scores
            algorithm: Algorithm name (dbscan/kmeans)
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save cluster assignments
        output_file = f"{self.output_dir}/cluster_assignments_{algorithm}_{timestamp}.json"
        cluster_data = pdf[['id', 'timestamp', 'borough', 'neighborhood', 'lat', 'lon', 
                            'diseases', 'symptoms', 'severity', 'cluster_id' if 'cluster_id' in pdf else 'kmeans_cluster']].to_dict('records')

        with open(output_file, 'w') as f:
            json.dump(cluster_data, f, indent=2, default=str)
        logger.info(f"Saved cluster assignments to {output_file}")

        # Save cluster analysis
        analysis_file = f"{self.output_dir}/cluster_analysis_{algorithm}_{timestamp}.json"
        combined_analysis = {
            'metadata': {
                'algorithm': algorithm,
                'timestamp': timestamp,
                'total_records': len(pdf),
                'num_clusters': len(cluster_analysis)
            },
            'clusters': cluster_analysis,
            'semantic_scores': semantic_scores
        }

        with open(analysis_file, 'w') as f:
            json.dump(combined_analysis, f, indent=2, default=str)
        logger.info(f"Saved cluster analysis to {analysis_file}")

        # Save summary statistics
        summary_file = f"{self.output_dir}/cluster_summary_{algorithm}_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"={'='*70}\n")
            f.write(f"Spatial Clustering Analysis Summary - {algorithm.upper()}\n")
            f.write(f"Generated: {timestamp}\n")
            f.write(f"={'='*70}\n\n")

            f.write(f"Total Records: {len(pdf)}\n")
            f.write(f"Number of Clusters: {len(cluster_analysis)}\n\n")

            for cluster_id, analysis in sorted(cluster_analysis.items()):
                f.write(f"\n{'='*70}\n")
                f.write(f"CLUSTER {cluster_id}\n")
                f.write(f"{'='*70}\n")
                f.write(f"Size: {analysis['size']} records\n")
                f.write(f"Centroid: lat={analysis['centroid']['lat']:.4f}, lon={analysis['centroid']['lon']:.4f}\n\n")

                f.write(f"Boroughs:\n")
                for borough, count in sorted(analysis['boroughs'].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"  - {borough}: {count}\n")

                f.write(f"\nTop Neighborhoods:\n")
                for neighborhood, count in sorted(analysis['neighborhoods'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    f.write(f"  - {neighborhood}: {count}\n")

                f.write(f"\nTop Diseases:\n")
                for disease, count in sorted(analysis['diseases'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    f.write(f"  - {disease}: {count}\n")

                f.write(f"\nTop Symptoms:\n")
                for symptom, count in sorted(analysis['symptoms'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    f.write(f"  - {symptom}: {count}\n")

                f.write(f"\nSeverity Distribution:\n")
                for severity, count in sorted(analysis['severity'].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"  - {severity}: {count}\n")

                if cluster_id in semantic_scores and semantic_scores[cluster_id]['avg_cosine_similarity']:
                    f.write(f"\nSemantic Coherence: {semantic_scores[cluster_id]['semantic_coherence']}")
                    f.write(f" (similarity: {semantic_scores[cluster_id]['avg_cosine_similarity']:.3f})\n")

                f.write(f"\nTime Range: {analysis['time_range']['start']} to {analysis['time_range']['end']}\n")

        logger.info(f"Saved cluster summary to {summary_file}")

    def run_analysis(
        self,
        algorithm: str = 'dbscan',
        time_window_days: Optional[int] = 90,
        disease_filter: Optional[List[str]] = None,
        borough_filter: Optional[List[str]] = None,
        **clustering_params
    ):
        """
        Run complete spatial clustering analysis

        Args:
            algorithm: 'dbscan' or 'kmeans'
            time_window_days: Filter to last N days
            disease_filter: List of diseases to include
            borough_filter: List of boroughs to include
            **clustering_params: Algorithm-specific parameters
                - For DBSCAN: eps_km (default 2.0), min_samples (default 5)
                - For K-Means: n_clusters (default 5)
        """
        logger.info("="*70)
        logger.info("Starting Spatial Clustering Analysis")
        logger.info(f"Algorithm: {algorithm.upper()}")
        logger.info("="*70)

        # Load data from TimescaleDB
        df = self.load_data_from_timescaledb(
            time_window_days=time_window_days,
            disease_filter=disease_filter,
            borough_filter=borough_filter
        )

        if df.count() == 0:
            logger.error("No data to cluster. Exiting.")
            return

        # Prepare spatial features
        pdf = self.prepare_spatial_features(df)

        if len(pdf) < 2:
            logger.error("Insufficient data for clustering. Exiting.")
            return

        # Run clustering
        if algorithm.lower() == 'dbscan':
            eps_km = clustering_params.get('eps_km', 2.0)
            min_samples = clustering_params.get('min_samples', 5)
            pdf = self.dbscan_clustering(pdf, eps_km=eps_km, min_samples=min_samples)
            cluster_col = 'cluster_id'
        elif algorithm.lower() == 'kmeans':
            n_clusters = clustering_params.get('n_clusters', 5)
            pdf = self.kmeans_clustering(pdf, n_clusters=n_clusters)
            cluster_col = 'kmeans_cluster'
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}. Use 'dbscan' or 'kmeans'")

        # Analyze clusters
        cluster_analysis = self.analyze_clusters(pdf, cluster_col=cluster_col)

        # Enrich with semantic similarity
        semantic_scores = self.enrich_with_semantic_similarity(pdf, cluster_col=cluster_col)

        # Save results
        self.save_results(pdf, cluster_analysis, semantic_scores, algorithm)

        # Print summary
        logger.info("\n" + "="*70)
        logger.info("CLUSTERING SUMMARY")
        logger.info("="*70)
        logger.info(f"Algorithm: {algorithm.upper()}")
        logger.info(f"Total records: {len(pdf)}")
        logger.info(f"Number of clusters: {len(cluster_analysis)}")
        logger.info(f"Results saved to: {self.output_dir}/")
        logger.info("="*70)

    def stop(self):
        """Stop Spark session"""
        self.spark.stop()
        logger.info("Spark session stopped")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Spatial Clustering for Disease Surveillance')
    parser.add_argument('--algorithm', default='dbscan', choices=['dbscan', 'kmeans'],
                        help='Clustering algorithm')
    parser.add_argument('--time-window', type=int, default=90,
                        help='Time window in days (default: 90, use 0 for all data)')
    parser.add_argument('--disease', type=str, nargs='+',
                        help='Filter by diseases (e.g., COVID-19 Influenza)')
    parser.add_argument('--borough', type=str, nargs='+',
                        help='Filter by boroughs (e.g., Manhattan Brooklyn)')
    
    # DBSCAN parameters
    parser.add_argument('--eps-km', type=float, default=2.0,
                        help='DBSCAN epsilon in km (default: 2.0)')
    parser.add_argument('--min-samples', type=int, default=5,
                        help='DBSCAN minimum samples (default: 5)')
    
    # K-Means parameters
    parser.add_argument('--k', type=int, default=5,
                        help='K-Means number of clusters (default: 5)')
    
    # Database config
    parser.add_argument('--postgres-host', default='localhost')
    parser.add_argument('--postgres-port', type=int, default=5432)
    parser.add_argument('--chromadb-path', default='data/chromadb')
    parser.add_argument('--output-dir', default='data/spatial_clusters')

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = SpatialClusteringAnalyzer(
        postgres_host=args.postgres_host,
        postgres_port=args.postgres_port,
        chromadb_path=args.chromadb_path,
        output_dir=args.output_dir
    )

    # Prepare clustering parameters
    clustering_params = {}
    if args.algorithm == 'dbscan':
        clustering_params = {
            'eps_km': args.eps_km,
            'min_samples': args.min_samples
        }
    elif args.algorithm == 'kmeans':
        clustering_params = {
            'n_clusters': args.k
        }

    # Run analysis
    try:
        analyzer.run_analysis(
            algorithm=args.algorithm,
            time_window_days=args.time_window if args.time_window > 0 else None,
            disease_filter=args.disease,
            borough_filter=args.borough,
            **clustering_params
        )
    finally:
        analyzer.stop()


if __name__ == "__main__":
    main()
