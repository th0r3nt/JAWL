"""
Семантический модуль для Байесовских гипотез.
Форматирует список активных гипотез и лог улик для системного промпта.
"""

from typing import List
from src.utils.dtime import format_timestamp
from src.l1_databases.sql.tables import BayesianHypothesisTable


def build_hypotheses(
    hypotheses: List[BayesianHypothesisTable],
    max_clusters: int,
    max_hypotheses: int,
    tz_offset: int,
) -> str:
    """
    Формирует Markdown ASCII-дерево кластеров активных гипотез.
    """
    if not hypotheses:
        return ""

    # Группируем гипотезы по кластерам
    clusters = {}
    for h in hypotheses:
        c_name = h.cluster_name or "Общее расследование"
        clusters.setdefault(c_name, []).append(h)

    lines = [
        "## CLUSTERS OF HYPOTHESES",
        f"Max active clusters: {max_clusters} | Total max hypotheses: {max_hypotheses}",
        "Recommended to use these clusters for directed deduction.\n",
    ]

    for c_name, hyps in clusters.items():
        lines.append(f'[Cluster]: "{c_name}"')
        lines.append("  │")

        for i, h in enumerate(hyps):
            is_last_hyp = i == len(hyps) - 1
            hyp_connector = "└─" if is_last_hyp else "├─"
            hyp_pipe = "     " if is_last_hyp else "  │  "

            prob_percent = int(h.current_probability * 100)
            prior_percent = int(h.prior_probability * 100)
            time_str = format_timestamp(h.updated_at.timestamp(), tz_offset, "%H:%M")

            lines.append(
                f'  {hyp_connector} [ID: {h.id}] Hypothesis: "{h.title}" | Confidence: {prob_percent}% (Initial: {prior_percent}%) | Updated: {time_str}'
            )

            if h.evidence_log:
                recent_evidence = h.evidence_log[-6:]
                if len(h.evidence_log) > 6:
                    lines.append(
                        f"{hyp_pipe}  ... (skipped {len(h.evidence_log) - 6} old pieces of evidence)"
                    )

                for j, ev in enumerate(recent_evidence):
                    is_last_ev = j == len(recent_evidence) - 1
                    ev_connector = "└─" if is_last_ev else "├─"
                    tpr_pct = int(ev["tpr"] * 100)
                    fpr_pct = int(ev["fpr"] * 100)
                    new_prob_pct = int(ev["new_prob"] * 100)

                    old_prob = ev.get("old_prob")
                    if old_prob is not None:
                        old_pct = int(old_prob * 100)
                        transition = f"Became: {old_pct}% -> {new_prob_pct}%"
                    else:
                        transition = f"Became: {new_prob_pct}%"

                    lines.append(
                        f"{hyp_pipe}  {ev_connector} [+] \"{ev['evidence']}\" (TPR: {tpr_pct}%, FPR: {fpr_pct}%) -> {transition}"
                    )
            else:
                lines.append(f"{hyp_pipe}  └─ [Empty. Awaiting evidence collection]")

        lines.append("")

    return "\n".join(lines).strip()
