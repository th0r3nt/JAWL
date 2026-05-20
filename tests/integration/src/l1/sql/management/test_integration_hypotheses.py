"""
Интеграционные тесты для модуля вероятностного мышления (Bayesian Hypotheses).
Проверяют корректность работы CRUD операций в SQLite и математику Теоремы Байеса.
"""

import pytest


def test_hypotheses_calculate_posterior(hypotheses_manager):
    """
    Тест: Математика Теоремы Байеса и Правила Кромвеля (защита от 0% и 100%).
    Формула: P(H|E) = (TPR * Prior) / (TPR * Prior + FPR * (1 - Prior))
    """
    # Классический пример:
    # Вероятность ДО (Prior): 30% (0.3)
    # Вероятность встретить улику, если гипотеза верна (TPR): 80% (0.8)
    # Вероятность встретить улику случайно (FPR): 10% (0.1)
    # Результат: (0.8 * 0.3) / (0.8 * 0.3 + 0.1 * 0.7) = 0.24 / 0.31 ≈ 0.774
    posterior = hypotheses_manager._calculate_posterior(prior=0.3, tpr=0.8, fpr=0.1)
    assert 0.77 <= posterior <= 0.78

    # Тест Правила Кромвеля: Агент никогда не должен быть уверен на 100% (из-за деления на 0).
    # Иначе он попадет в "Байесовский лок" и перестанет воспринимать новые факты.
    posterior_extreme = hypotheses_manager._calculate_posterior(
        prior=0.999, tpr=0.999, fpr=0.001
    )
    assert posterior_extreme <= 0.99


@pytest.mark.asyncio
async def test_hypotheses_crud_lifecycle(hypotheses_manager):
    """Тест: Полный жизненный цикл гипотезы (Создание -> Улика -> Удаление)."""

    # 1. Создание
    res_add = await hypotheses_manager.formulate_hypothesis(
        "Инцидент 1", "Сервер упал из-за DDoS", 0.5
    )
    assert res_add.is_success is True
    # assert "Текущая уверенность: 50%" in res_add.message

    # Извлекаем ID из сообщения
    hyp_id = res_add.message.split("ID: ")[1].split(")")[0].strip()

    # Проверка, что она попала в системный промпт
    context_initial = await hypotheses_manager.get_context_block()
    assert "Сервер упал из-за DDoS" in context_initial
    assert "Confidence: 50%" in context_initial

    res_evidence = await hypotheses_manager.add_evidence(
        hypothesis_id=hyp_id,
        evidence_desc="Трафик вырос в 100 раз",
        true_positive_rate=0.9,
        false_positive_rate=0.1,
    )
    assert res_evidence.is_success is True
    # assert "Вероятность гипотезы" in res_evidence.message
    # assert "50% -> 90%" in res_evidence.message

    # Проверка, что лог улик отрендерился в промпт
    context_updated = await hypotheses_manager.get_context_block()
    assert "Трафик вырос в 100 раз" in context_updated
    assert "TPR: 90%, FPR: 10%" in context_updated
    assert "Became: 50% -> 90%" in context_updated

    # 3. Закрытие (Разрешение) гипотезы
    res_resolve = await hypotheses_manager.resolve_hypothesis(hyp_id)
    assert res_resolve.is_success is True

    # Контекст должен очиститься
    context_empty = await hypotheses_manager.get_context_block()
    assert context_empty == ""


@pytest.mark.asyncio
async def test_hypotheses_limits(hypotheses_manager):
    """Тест: Защита от переполнения оперативной памяти (лимиты гипотез и кластеров)."""

    # В фикстуре max_clusters=2, max_hypotheses=4
    await hypotheses_manager.formulate_hypothesis("Кластер 1", "H1", 0.5)
    await hypotheses_manager.formulate_hypothesis("Кластер 2", "H2", 0.5)

    # 1. Тест лимита кластеров
    res_fail_cluster = await hypotheses_manager.formulate_hypothesis("Кластер 3", "H3", 0.5)
    assert res_fail_cluster.is_success is False
    assert "Достигнут лимит уникальных кластеров" in res_fail_cluster.message

    # 2. Тест глобального лимита гипотез
    await hypotheses_manager.formulate_hypothesis("Кластер 1", "H3", 0.5)
    await hypotheses_manager.formulate_hypothesis("Кластер 2", "H4", 0.5)

    res_fail_hyp = await hypotheses_manager.formulate_hypothesis("Кластер 1", "H5", 0.5)
    assert res_fail_hyp.is_success is False
    assert "Достигнут глобальный лимит" in res_fail_hyp.message


@pytest.mark.asyncio
async def test_hypotheses_validation(hypotheses_manager):
    """Тест: Защита от галлюцинаций LLM при вводе вероятностей."""

    # Вероятность больше 1
    res_high = await hypotheses_manager.formulate_hypothesis("Кластер 1", "H", 1.5)
    assert res_high.is_success is False
    assert "между 0.01 и 0.99" in res_high.message

    # Вероятность меньше 0
    res_low = await hypotheses_manager.formulate_hypothesis("Кластер 1", "H", -0.5)
    assert res_low.is_success is False
