#!/usr/bin/env python3
"""Build the RAG knowledge base index.

Usage:
    python build_kb.py                    # Build production data only (default)
    python build_kb.py --type production  # Build production data only
    python build_kb.py --type all         # Build all data (production + test)
    python build_kb.py --config 2         # Build from specific AI config ID

This script:
1. Loads the specified AI config (must have embedding_model set)
2. Chunks all requirements, modules, and test cases from the database
3. Calls the Embedding API to generate vectors
4. Stores vectors in the embeddings table
"""
import sys
import os

# Add backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models.ai_config import AIConfig
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RAGService


def main():
    app = create_app()
    with app.app_context():
        # Parse --config argument
        config_id = None
        if "--config" in sys.argv:
            idx = sys.argv.index("--config")
            if idx + 1 < len(sys.argv):
                config_id = int(sys.argv[idx + 1])

        # Parse --type argument (production/test/all)
        project_type = "production"
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            if idx + 1 < len(sys.argv):
                val = sys.argv[idx + 1]
                if val.lower() == "all":
                    project_type = None
                else:
                    project_type = val

        # Find AI config
        if config_id:
            config = AIConfig.query.get(config_id)
            if not config:
                print(f"Error: AI config with id={config_id} not found")
                sys.exit(1)
        else:
            config = AIConfig.get_default_embedding_config()
            if not config:
                print("Error: No active default embedding configuration found.")
                print("Please configure an embedding model in the web UI first.")
                sys.exit(1)

        print(f"Using AI config: id={config.id} name={config.name}")
        print(f"  Chat model: {config.model}")
        print(f"  Embedding model: {config.embedding_model or '(not set)'}")
        print(f"  Project type: {project_type or 'all'}")

        if not config.embedding_model:
            print("\nError: Embedding model is not configured for this AI config.")
            print("Please set an embedding_model in the AI Config page.")
            sys.exit(1)

        # Confirm before proceeding
        from app.models.requirement import Requirement
        from app.models.module import Module
        from app.models.test_case import TestCase

        if project_type:
            req_count = Requirement.query.filter_by(project_type=project_type).count()
            mod_count = Module.query.join(
                Requirement, Module.requirement_id == Requirement.id
            ).filter(Requirement.project_type == project_type).count()
            case_count = TestCase.query.join(
                Module, TestCase.module_id == Module.id
            ).join(
                Requirement, Module.requirement_id == Requirement.id
            ).filter(Requirement.project_type == project_type).count()
        else:
            req_count = Requirement.query.count()
            mod_count = Module.query.count()
            case_count = TestCase.query.count()
        total = req_count + mod_count + case_count

        print(f"\nKnowledge base data:")
        print(f"  Requirements: {req_count}")
        print(f"  Modules: {mod_count}")
        print(f"  Test cases: {case_count}")
        print(f"  Total chunks: {total}")

        if total == 0:
            print("\nNo data found. Please add requirements and generate test cases first.")
            sys.exit(0)

        answer = input(f"\nThis will clear existing embeddings and re-embed {total} chunks. Continue? (y/N): ")
        if answer.lower() != "y":
            print("Aborted.")
            sys.exit(0)

        # Build index
        print("\nBuilding knowledge base index...")
        rag = RAGService(config, user_id=None)
        result = rag.rebuild(project_type=project_type)

        print(f"\nDone!")
        print(f"  Status: {result['status']}")
        print(f"  Chunks stored: {result['chunk_count']}")
        print(f"  Vector dimension: {result['dim']}")
        print(f"  Time elapsed: {result['elapsed_ms']}ms")
        print("\nKnowledge base is ready for RAG queries.")


if __name__ == "__main__":
    main()
