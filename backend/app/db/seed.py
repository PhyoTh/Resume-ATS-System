"""Seed common skill aliases so the dashboard starts consistent on day 0."""
from sqlalchemy.orm import Session

from app.db.models import EntityAlias

SEED_SKILL_ALIASES = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python3": "Python",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "pg": "PostgreSQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "nodejs": "Node.js",
    "node": "Node.js",
    "reactjs": "React",
    "react.js": "React",
    "nextjs": "Next.js",
    "next": "Next.js",
    "tf": "TensorFlow",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "gcp": "Google Cloud",
    "aws": "AWS",
    "amazon web services": "AWS",
    "ml": "Machine Learning",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",
    "db": "Databases",
    "sql": "SQL",
    "nosql": "NoSQL",
    "c++": "C++",
    "cpp": "C++",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "java": "Java",
    "rest": "REST APIs",
    "graphql": "GraphQL",
    "ci/cd": "CI/CD",
    "ci": "CI/CD",
    "cicd": "CI/CD",
}


def seed_aliases(db: Session) -> int:
    existing = {
        (a.alias, a.kind)
        for a in db.query(EntityAlias).filter(EntityAlias.kind == "skill").all()
    }
    added = 0
    for alias, canonical in SEED_SKILL_ALIASES.items():
        key = (alias.lower(), "skill")
        if key in existing:
            continue
        db.add(
            EntityAlias(
                alias=alias.lower(), kind="skill", canonical=canonical, source="seed", frequency=0
            )
        )
        added += 1
    db.commit()
    return added
