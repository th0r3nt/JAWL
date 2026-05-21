"""
CRUD controller for Bayesian hypotheses.
Implements probability recalculation mathematics (Bayes' Theorem) and protection against "Bayesian Lock" (Cromwell's Rule).
"""

import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, delete, func, text

from src.utils.logger import main_logger
from src.l1_databases.sql.tables import BayesianHypothesisTable
from src.l1_databases.sql.management.hypotheses.semantics import build_hypotheses
from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLHypotheses:
    """
    Probabilistic deduction controller.
    """

    def __init__(
        self, db: "SQLDB", max_clusters: int = 3, max_hypotheses: int = 10, tz_offset: int = 0
    ) -> None:
        self.db = db
        self.max_clusters = max_clusters
        self.max_hypotheses = max_hypotheses
        self.tz_offset = tz_offset

    async def bootstrap_migrations(self) -> None:
        """
        Soft migration to add cluster_name column to older databases.
        """
        async with self.db.engine.begin() as conn:
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE bayesian_hypotheses ADD COLUMN cluster_name TEXT DEFAULT 'General investigation'"
                    )
                )
                main_logger.info(
                    "[SQL DB] Successful migration of the BayesianHypotheses table (added cluster_name)."
                )
            except Exception as e:
                main_logger.debug(
                    f"[SQL DB] Migration of the Tasks table skipped (column probably already exists): {e}"
                )

    def _calculate_posterior(self, prior: float, tpr: float, fpr: float) -> float:
        """
        Bayes' Theorem.
        P(H|E) = (TPR * Prior) / (TPR * Prior + FPR * (1 - Prior))
        """

        # Cromwell's Rule: clip probabilities to avoid division by zero
        # and irreversible 100% confidence (leaving a chance for miracle/error)
        prior = max(0.01, min(0.99, prior))
        tpr = max(0.01, min(0.99, tpr))
        fpr = max(0.01, min(0.99, fpr))

        numerator = tpr * prior
        denominator = numerator + fpr * (1.0 - prior)

        if denominator == 0:
            return prior

        posterior = numerator / denominator
        return max(0.01, min(0.99, posterior))

    @skill()
    async def formulate_hypothesis(
        self, cluster_name: str, title: str, initial_probability: float
    ) -> SkillResult:
        """
        Formulates hypothesis for directed investigation.

        cluster_name: Incident name.
        title: Core thesis.
        initial_probability: Base confidence (0.01-0.99).
        """

        if not (0.01 <= initial_probability <= 0.99):
            return SkillResult.fail(
                "Error: initial probability must be between 0.01 and 0.99."
            )

        clean_cluster = cluster_name.strip()
        if not clean_cluster:
            clean_cluster = "General investigation"

        hyp_id = str(uuid.uuid4())[:4]

        async with self.db.session_factory() as session:
            # 1. Check global hypotheses limit
            count_res = await session.execute(select(func.count(BayesianHypothesisTable.id)))
            if count_res.scalar_one() >= self.max_hypotheses:
                return SkillResult.fail(
                    f"Global active hypotheses limit reached ({self.max_hypotheses}). It is recommended to delete confirmed/refuted ones."
                )

            # 2. Check unique clusters limit
            clusters_res = await session.execute(
                select(BayesianHypothesisTable.cluster_name).distinct()
            )
            existing_clusters = {row[0] for row in clusters_res.all()}

            if (
                clean_cluster not in existing_clusters
                and len(existing_clusters) >= self.max_clusters
            ):
                return SkillResult.fail(
                    f"Unique hypothesis clusters limit reached ({self.max_clusters}). "
                    f"It is recommended to close old hypotheses to clear the cluster."
                )

            new_hyp = BayesianHypothesisTable(
                id=hyp_id,
                cluster_name=clean_cluster,
                title=title.strip(),
                prior_probability=initial_probability,
                current_probability=initial_probability,
                evidence_log=[],
            )
            session.add(new_hyp)
            await session.commit()

        msg = f"Hypothesis '{title}' formulated (ID: {hyp_id}). Current confidence: {int(initial_probability * 100)}%."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(f"True. ID: {hyp_id}")

    @skill()
    async def add_evidence(
        self,
        hypothesis_id: str,
        evidence_desc: str,
        true_positive_rate: float,
        false_positive_rate: float,
    ) -> SkillResult:
        """
        Adds evidence and recalculates Bayesian probability.

        evidence_desc: Found fact.
        true_positive_rate: (0.01-0.99) Prob if hypothesis true.
        false_positive_rate: (0.01-0.99) Prob if hypothesis false.
        """

        if not (0.01 <= true_positive_rate <= 0.99) or not (
            0.01 <= false_positive_rate <= 0.99
        ):
            return SkillResult.fail("Error: TPR and FPR must be in the range of 0.01 to 0.99.")

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(BayesianHypothesisTable).where(
                    BayesianHypothesisTable.id == hypothesis_id
                )
            )
            hyp = result.scalar_one_or_none()

            if not hyp:
                return SkillResult.fail(f"Hypothesis with ID '{hypothesis_id}' not found.")

            old_prob = hyp.current_probability
            new_prob = self._calculate_posterior(
                old_prob, true_positive_rate, false_positive_rate
            )

            # Update DB (create a new list for correct JSON serialization in SQLAlchemy)
            current_log = list(hyp.evidence_log)
            current_log.append(
                {
                    "evidence": evidence_desc.strip(),
                    "tpr": true_positive_rate,
                    "fpr": false_positive_rate,
                    "old_prob": old_prob,
                    "new_prob": new_prob,
                }
            )

            hyp.evidence_log = current_log
            hyp.current_probability = new_prob

            await session.commit()

        msg = f"Fact added. Probability of hypothesis '{hyp.title}' changed: {int(old_prob*100)}% -> {int(new_prob*100)}%."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill()
    async def resolve_hypothesis(self, hypothesis_id: str) -> SkillResult:
        """
        Deletes resolved (confirmed/refuted) hypothesis.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                delete(BayesianHypothesisTable).where(
                    BayesianHypothesisTable.id == hypothesis_id
                )
            )
            await session.commit()
            if result.rowcount == 0:
                return SkillResult.fail(f"Hypothesis with ID '{hypothesis_id}' not found.")

        msg = (
            f"Hypothesis '{hypothesis_id}' successfully closed and removed from active memory."
        )
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Block for the agent's system prompt.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(BayesianHypothesisTable))
            hypotheses = result.scalars().all()

        return build_hypotheses(
            hypotheses, self.max_clusters, self.max_hypotheses, self.tz_offset
        )
