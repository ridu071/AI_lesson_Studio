"""Shared helpers for tests."""


def build_qc_input(lesson: dict, research: dict):
    """Turn (possibly modified) fixture dicts into a QCInput."""
    from app.modules.qc.schemas import QCInput

    return QCInput(
        request_objective=(
            "Differentiate supervised and unsupervised learning and identify "
            "real-world applications of both."
        ),
        lesson=lesson,
        research=research,
    )
