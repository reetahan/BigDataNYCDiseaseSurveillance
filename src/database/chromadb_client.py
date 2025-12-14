"""
ChromaDB Client for NYC Disease Surveillance
Loads vector embeddings into ChromaDB for semantic search and analysis
"""

import os
import json
import glob
from typing import List, Dict, Optional
import logging
from datetime import datetime

import chromadb
from chromadb.config import Settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChromaDBClient:
    """
    Client for loading disease surveillance embeddings into ChromaDB
    """

    def __init__(
        self,
        persist_directory: str = "data/chromadb",
        collection_name: str = "nyc_disease_surveillance"
    ):
        """
        Initialize ChromaDB client

        Args:
            persist_directory: Directory to persist ChromaDB data
            collection_name: Name of the ChromaDB collection
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        # Create persist directory
        os.makedirs(self.persist_directory, exist_ok=True)

        # Initialize ChromaDB client
        logger.info(f"Initializing ChromaDB at: {self.persist_directory}")
        self.client = chromadb.PersistentClient(path=self.persist_directory)

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "NYC Disease Surveillance Embeddings"}
        )

        logger.info(f"Connected to collection: {self.collection_name}")
        logger.info(f"Current collection size: {self.collection.count()} documents")

    def load_embeddings_from_file(self, embeddings_file: str) -> int:
        """
        Load embeddings from a single JSON file into ChromaDB

        Args:
            embeddings_file: Path to embeddings JSON file

        Returns:
            Number of documents loaded
        """
        logger.info(f"Loading embeddings from: {embeddings_file}")

        with open(embeddings_file, 'r') as f:
            embeddings_data = json.load(f)

        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        metadatas = []
        documents = []

        for doc in embeddings_data:
            ids.append(doc['id'])
            embeddings.append(doc['vector'])
            documents.append(doc['text'])

            # Flatten metadata for ChromaDB (convert lists to strings)
            metadata = doc['metadata'].copy()

            # Convert list fields to comma-separated strings
            if 'diseases' in metadata and isinstance(metadata['diseases'], list):
                metadata['diseases'] = ','.join(metadata['diseases'])
            if 'symptoms' in metadata and isinstance(metadata['symptoms'], list):
                metadata['symptoms'] = ','.join(metadata['symptoms'])

            # Add embedding metadata
            metadata['embedding_model'] = doc['embedding_model']
            metadata['embedding_dim'] = doc['embedding_dim']
            metadata['created_at'] = doc['created_at']

            # Remove None values (ChromaDB doesn't like them)
            metadata = {k: v for k, v in metadata.items() if v is not None}

            metadatas.append(metadata)

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )

        logger.info(f"Added {len(ids)} documents to ChromaDB")
        return len(ids)

    def load_embeddings_from_directory(self, embeddings_dir: str) -> int:
        """
        Load all embedding files from a directory into ChromaDB

        Args:
            embeddings_dir: Directory containing embedding JSON files

        Returns:
            Total number of documents loaded
        """
        logger.info(f"Loading embeddings from directory: {embeddings_dir}")

        # Find all embedding files (not summary files)
        file_pattern = os.path.join(embeddings_dir, "embeddings_batch_*.json")
        embedding_files = glob.glob(file_pattern)

        logger.info(f"Found {len(embedding_files)} embedding files")

        total_loaded = 0
        for file_path in embedding_files:
            try:
                count = self.load_embeddings_from_file(file_path)
                total_loaded += count
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")

        logger.info(f"Total documents loaded: {total_loaded}")
        logger.info(f"Collection size: {self.collection.count()}")
        return total_loaded

    def query(
        self,
        query_texts: List[str],
        n_results: int = 10,
        where: Optional[Dict] = None,
        where_document: Optional[Dict] = None
    ) -> Dict:
        """
        Query the ChromaDB collection

        Args:
            query_texts: List of query strings
            n_results: Number of results to return
            where: Metadata filter (e.g., {"borough": "Brooklyn"})
            where_document: Document content filter

        Returns:
            Query results
        """
        results = self.collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where=where,
            where_document=where_document
        )
        return results

    def search_by_disease(
        self,
        query_text: str,
        disease: str,
        n_results: int = 10
    ) -> Dict:
        """
        Search for outbreaks related to a specific disease

        Args:
            query_text: Natural language query
            disease: Disease name to filter by
            n_results: Number of results

        Returns:
            Query results
        """
        logger.info(f"Searching for disease: {disease}")

        # ChromaDB metadata filtering with contains
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where_document={"$contains": disease}
        )
        return results

    def search_by_location(
        self,
        query_text: str,
        borough: Optional[str] = None,
        neighborhood: Optional[str] = None,
        n_results: int = 10
    ) -> Dict:
        """
        Search for outbreaks in a specific location

        Args:
            query_text: Natural language query
            borough: Borough name (e.g., "Brooklyn")
            neighborhood: Neighborhood name (e.g., "Williamsburg")
            n_results: Number of results

        Returns:
            Query results
        """
        where_filter = {}
        if borough:
            where_filter['borough'] = borough
        if neighborhood:
            where_filter['neighborhood'] = neighborhood

        logger.info(f"Searching in location: {where_filter}")

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_filter if where_filter else None
        )
        return results

    def search_by_severity(
        self,
        query_text: str,
        severity: str,
        n_results: int = 10
    ) -> Dict:
        """
        Search for outbreaks by severity level

        Args:
            query_text: Natural language query
            severity: Severity level (low/medium/high)
            n_results: Number of results

        Returns:
            Query results
        """
        logger.info(f"Searching for severity: {severity}")

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"severity": severity}
        )
        return results

    def get_statistics(self) -> Dict:
        """
        Get collection statistics

        Returns:
            Dictionary with collection stats
        """
        count = self.collection.count()

        # Get a sample to analyze metadata
        sample = self.collection.get(limit=min(100, count))

        stats = {
            "total_documents": count,
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory
        }

        # Analyze metadata if we have documents
        if sample and sample['metadatas']:
            unique_diseases = set()
            unique_boroughs = set()
            severity_counts = {}

            for meta in sample['metadatas']:
                if 'diseases' in meta and meta['diseases']:
                    unique_diseases.update(meta['diseases'].split(','))
                if 'borough' in meta and meta['borough']:
                    unique_boroughs.add(meta['borough'])
                if 'severity' in meta and meta['severity']:
                    severity = meta['severity']
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1

            stats['sample_diseases'] = list(unique_diseases)
            stats['sample_boroughs'] = list(unique_boroughs)
            stats['severity_distribution'] = severity_counts

        return stats

    def clear_collection(self):
        """
        Delete all documents from the collection
        """
        logger.warning(f"Clearing collection: {self.collection_name}")
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "NYC Disease Surveillance Embeddings"}
        )
        logger.info("Collection cleared")


def main():
    """Main entry point for loading embeddings into ChromaDB"""
    import argparse

    parser = argparse.ArgumentParser(description='Load embeddings into ChromaDB')
    parser.add_argument('--embeddings-dir', default='data/embeddings',
                        help='Directory containing embedding files')
    parser.add_argument('--persist-dir', default='data/chromadb',
                        help='ChromaDB persist directory')
    parser.add_argument('--collection', default='nyc_disease_surveillance',
                        help='Collection name')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing collection before loading')
    parser.add_argument('--query', type=str,
                        help='Run a test query after loading')

    args = parser.parse_args()

    # Initialize ChromaDB client
    chroma_client = ChromaDBClient(
        persist_directory=args.persist_dir,
        collection_name=args.collection
    )

    # Clear if requested
    if args.clear:
        chroma_client.clear_collection()

    # Load embeddings
    logger.info("="*60)
    logger.info("Loading Embeddings into ChromaDB")
    logger.info("="*60)

    total_loaded = chroma_client.load_embeddings_from_directory(args.embeddings_dir)

    # Print statistics
    stats = chroma_client.get_statistics()
    logger.info("\n" + "="*60)
    logger.info("ChromaDB Statistics")
    logger.info("="*60)
    logger.info(f"Total Documents: {stats['total_documents']}")
    logger.info(f"Collection: {stats['collection_name']}")

    if 'sample_diseases' in stats:
        logger.info(f"Diseases (sample): {', '.join(stats['sample_diseases'][:10])}")
    if 'sample_boroughs' in stats:
        logger.info(f"Boroughs: {', '.join(stats['sample_boroughs'])}")
    if 'severity_distribution' in stats:
        logger.info(f"Severity Distribution: {stats['severity_distribution']}")

    # Run test query if provided
    if args.query:
        logger.info("\n" + "="*60)
        logger.info(f"Test Query: '{args.query}'")
        logger.info("="*60)

        results = chroma_client.query(
            query_texts=[args.query],
            n_results=5
        )

        for i, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        )):
            logger.info(f"\nResult {i+1} (distance: {distance:.4f}):")
            logger.info(f"  Text: {doc[:200]}...")
            logger.info(f"  Disease: {metadata.get('diseases', 'N/A')}")
            logger.info(f"  Location: {metadata.get('neighborhood', 'N/A')}, {metadata.get('borough', 'N/A')}")
            logger.info(f"  Severity: {metadata.get('severity', 'N/A')}")

    logger.info("\n✓ ChromaDB loading completed successfully!")


if __name__ == "__main__":
    main()
