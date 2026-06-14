"""SQLAlchemy ORM models matching the lan.md init.sql schema."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Integer, Numeric, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship

from src.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    credits = Column(Integer, default=100, nullable=False)
    tier = Column(String, default="free", nullable=False)  # free | pro | enterprise
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)

    projects = relationship("Project", back_populates="user")
    llm_usage = relationship("LlmUsage", back_populates="user")
    model_configs = relationship("ModelConfig", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=True)
    initial_prompt = Column(Text, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending | running | paused | success | failed
    current_agent = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="projects")
    checkpoints = relationship("ProjectCheckpoint", back_populates="project", cascade="all, delete-orphan")
    llm_usage = relationship("LlmUsage", back_populates="project")


class ProjectCheckpoint(Base):
    __tablename__ = "project_checkpoints"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_project_version"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    state = Column(JSONB, nullable=False)
    agent = Column(String, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)

    project = relationship("Project", back_populates="checkpoints")


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agent = Column(String, nullable=False)
    model = Column(String, nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)

    project = relationship("Project", back_populates="llm_usage")
    user = relationship("User", back_populates="llm_usage")


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)      # anthropic | openai | deepseek | nvidia | custom
    model_name = Column(String, nullable=False)
    api_key_encrypted = Column(String, nullable=True)
    base_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    agent_assignment = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)

    user = relationship("User", back_populates="model_configs")
