"""
Семантический модуль для Байесовских гипотез.
Форматирует список активных гипотез и лог улик для системного промпта.
"""

from typing import List
from src.utils.dtime import format_timestamp
from src.l1_databases.sql.tables import BayesianHypothesisTable


def build_hypotheses(
    hypotheses: List[BayesianHypothesisTable], max_hypotheses: int, tz_offset: int
) -> str:
    """
    Формирует Markdown-блок активных гипотез.
    """
    if not hypotheses:
        return ""

    lines = [
        "## ACTIVE BAYESIAN HYPOTHESES",
        f"Max active hypotheses allowed: {max_hypotheses}",
        "Recommended to use these hypotheses for directed deduction.\n",
    ]

    for h in hypotheses:
        prob_percent = int(h.current_probability * 100)
        prior_percent = int(h.prior_probability * 100)

        time_str = format_timestamp(h.updated_at.timestamp(), tz_offset, "%H:%M")

        lines.append(f'[{h.id}] Hypothesis: "{h.title}"')
        lines.append(
            f"  * Confidence: {prob_percent}% (Initial: {prior_percent}%) | Updated: {time_str}"
        )

        if h.evidence_log:
            lines.append("  * Evidence Log:")
            # Показываем последние 6 улик, чтобы не выжигать контекст
            recent_evidence = h.evidence_log[-6:]
            if len(h.evidence_log) > 6:
                lines.append(
                    f"    ... (skipped {len(h.evidence_log) - 6} old pieces of evidence)"
                )

            for ev in recent_evidence:
                tpr_pct = int(ev["tpr"] * 100)
                fpr_pct = int(ev["fpr"] * 100)
                new_prob_pct = int(ev["new_prob"] * 100)
                lines.append(
                    f"    - [+] {ev['evidence']} (TPR: {tpr_pct}%, FPR: {fpr_pct}%) -> Became: {new_prob_pct}%"
                )
        else:
            lines.append("  * Evidence Log: [Empty. Awaiting evidence collection]")

        lines.append("")

    return "\n".join(lines).strip()
