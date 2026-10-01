import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.database import get_db
from app.main import create_app
from app.schemas.rag_schema import RAGAskResponse
from app.schemas.vector_schema import VectorSearchRequest
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService


def grouped_query(rows):
    query = MagicMock()
    query.filter.return_value = query
    query.group_by.return_value = query
    query.all.return_value = rows
    return query


class ProjectSourcesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_inventory_lists_only_grouped_project_sources(self):
        self.db.query.side_effect = [
            grouped_query([
                ("repository", "repo-a", "main", "abc123", 3),
                ("repository_metadata", "repo-a", None, None, 1),
            ]),
            grouped_query([("requisitos.pdf", "document", 2)]),
            grouped_query([("repo-a", "deadbeef123", "Agregar módulo", 2)]),
        ]

        response = self.client.get("/api/v1/projects/proyecto-1/sources")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "project_id": "proyecto-1",
            "repositories": [{
                "name": "repo-a",
                "chunks": 6,
                "branches": [{"name": "main", "commit": "abc123", "chunks": 3}],
                "commits": [{"sha": "deadbeef123", "message": "Agregar módulo", "chunks": 2}],
            }],
            "documents": [{
                "name": "requisitos.pdf",
                "artifact_type": "document",
                "chunks": 2,
            }],
            "total_chunks": 8,
        })

    def test_document_query_is_validated_and_passed_to_rag(self):
        query = MagicMock()
        query.filter.return_value = query
        query.first.side_effect = [(1,), (2,)]
        self.db.query.return_value = query
        answer = RAGAskResponse(
            answer="Respuesta",
            citations=[],
            context_chunks_used=0,
            retrieval_query="Pregunta",
            provider="test",
            model="test",
        )

        with patch("app.controllers.query_controller.RAGService.ask", return_value=answer) as ask:
            response = self.client.post("/api/v1/query", json={
                "project_id": "proyecto-1",
                "question": "Pregunta",
                "document": "requisitos.pdf",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ask.call_args.args[1].document, "requisitos.pdf")

        response = self.client.post("/api/v1/query", json={
            "project_id": "proyecto-1",
            "question": "Pregunta",
            "document": "requisitos.pdf",
            "branches": ["main"],
        })
        self.assertEqual(response.status_code, 422)

    def test_unknown_document_is_rejected_before_embedding(self):
        query = MagicMock()
        query.filter.return_value = query
        query.first.side_effect = [(1,), None]
        self.db.query.return_value = query

        with patch("app.controllers.query_controller.RAGService.ask") as ask:
            response = self.client.post("/api/v1/query", json={
                "project_id": "proyecto-1",
                "question": "Pregunta",
                "document": "inexistente.pdf",
            })

        self.assertEqual(response.status_code, 409)
        ask.assert_not_called()

    def test_vector_search_filters_document_inside_project(self):
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        with patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            VectorService.semantic_search(db, VectorSearchRequest(
                query="Pregunta",
                project_id="proyecto-1",
                document="requisitos, v1.pdf",
            ))

        predicates = " ".join(
            str(expression.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            ))
            for call in query.filter.call_args_list
            for expression in call.args
        )
        self.assertIn("'project_id'", predicates)
        self.assertIn("'proyecto-1'", predicates)
        self.assertIn("'source_type'", predicates)
        self.assertIn("'document'", predicates)
        self.assertIn("'requisitos, v1.pdf'", predicates)


if __name__ == "__main__":
    unittest.main()
