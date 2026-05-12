"""
CRUD-контроллер для Байесовских гипотез.
Реализует математику пересчета вероятности (Теорема Байеса) и защиту от "Байесовского лока" (Правило Кромвеля).
"""

import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, delete, func

from src.utils.logger import main_logger
from src.l1_databases.sql.tables import BayesianHypothesisTable
from src.l1_databases.sql.management.hypotheses.semantics import build_hypotheses
from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLHypotheses:
    """
    Контроллер вероятностной дедукции.
    """

    def __init__(self, db: "SQLDB", max_hypotheses: int = 5, tz_offset: int = 0) -> None:
        self.db = db
        self.max_hypotheses = max_hypotheses
        self.tz_offset = tz_offset

    def _calculate_posterior(self, prior: float, tpr: float, fpr: float) -> float:
        """
        Теорема Байеса.
        P(H|E) = (TPR * Prior) / (TPR * Prior + FPR * (1 - Prior))
        """

        # Правило Кромвеля: зажимаем вероятности, чтобы избежать деления на ноль
        # и необратимой 100% уверенности (оставляем шанс на чудо/ошибку)
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
        self, title: str, initial_probability: float
    ) -> SkillResult:
        """
        Создает новую гипотезу для направленного расследования.

        title: Суть гипотезы.
        initial_probability: Стартовая уверенность от 0.01 до 0.99 (например, 0.3 - 30%).
        """

        if not (0.01 <= initial_probability <= 0.99):
            return SkillResult.fail(
                "Ошибка: начальная вероятность должна быть между 0.01 и 0.99."
            )

        hyp_id = str(uuid.uuid4())[:4]

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(BayesianHypothesisTable.id)))
            if count_res.scalar_one() >= self.max_hypotheses:
                return SkillResult.fail(
                    f"Достигнут лимит активных гипотез ({self.max_hypotheses}). Сначала удалите подтвержденные/опровергнутые."
                )

            new_hyp = BayesianHypothesisTable(
                id=hyp_id,
                title=title.strip(),
                prior_probability=initial_probability,
                current_probability=initial_probability,
                evidence_log=[],
            )
            session.add(new_hyp)
            await session.commit()

        msg = f"Гипотеза '{title}' сформулирована (ID: {hyp_id}). Текущая уверенность: {int(initial_probability * 100)}%."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def add_evidence(
        self,
        hypothesis_id: str,
        evidence_desc: str,
        true_positive_rate: float,
        false_positive_rate: float,
    ) -> SkillResult:
        """
        Добавляет улику и автоматически пересчитывает математическую вероятность гипотезы (по Байесу).

        evidence_desc: Что за факт был обнаружен.
        true_positive_rate: (0.01 - 0.99). Вероятность встретить эту улику, если гипотеза верна.
        false_positive_rate: (0.01 - 0.99). Вероятность встретить эту улику, если гипотеза ошибочна (совпадение).
        """

        if not (0.01 <= true_positive_rate <= 0.99) or not (
            0.01 <= false_positive_rate <= 0.99
        ):
            return SkillResult.fail(
                "Ошибка: TPR и FPR должны быть в диапазоне от 0.01 до 0.99."
            )

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(BayesianHypothesisTable).where(
                    BayesianHypothesisTable.id == hypothesis_id
                )
            )
            hyp = result.scalar_one_or_none()

            if not hyp:
                return SkillResult.fail(f"Гипотеза с ID '{hypothesis_id}' не найдена.")

            old_prob = hyp.current_probability
            new_prob = self._calculate_posterior(
                old_prob, true_positive_rate, false_positive_rate
            )

            # Обновляем БД (создаем новый список для корректной сериализации JSON в SQLAlchemy)
            current_log = list(hyp.evidence_log)
            current_log.append(
                {
                    "evidence": evidence_desc.strip(),
                    "tpr": true_positive_rate,
                    "fpr": false_positive_rate,
                    "new_prob": new_prob,
                }
            )

            hyp.evidence_log = current_log
            hyp.current_probability = new_prob

            await session.commit()

        msg = f"Fact added. Вероятность гипотезы '{hyp.title}' изменилась: {int(old_prob*100)}% -> {int(new_prob*100)}%."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def resolve_hypothesis(self, hypothesis_id: str) -> SkillResult:
        """
        Удаляет гипотезу (после подтверждения или опровержения).
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                delete(BayesianHypothesisTable).where(
                    BayesianHypothesisTable.id == hypothesis_id
                )
            )
            await session.commit()
            if result.rowcount == 0:
                return SkillResult.fail(f"Гипотеза с ID '{hypothesis_id}' не найдена.")

        msg = f"Гипотеза '{hypothesis_id}' успешно закрыта и удалена из оперативной памяти."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Блок для системного промпта агента.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(BayesianHypothesisTable))
            hypotheses = result.scalars().all()

        return build_hypotheses(hypotheses, self.max_hypotheses, self.tz_offset)
