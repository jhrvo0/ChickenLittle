"""Proveniência da avaliação exploratória da UI, sem alterar seu contrato anterior."""


def preview_provenance(bundle, records):
    sessions = {r.session_id for r in records}
    participants = {r.participant_id for r in records}
    development = set(getattr(bundle, "development_sessions", ()))
    subjects = set(getattr(bundle, "development_participants", ()))
    if bundle.experimental_status == "RULES_NO_TRAINING":
        status = "rules_without_training"
    elif not development:
        status = "independence_unknown"
    elif sessions & development or (bundle.split_strategy == "by_participant" and subjects & participants):
        status = "overlaps_development"
    else:
        status = "independent_of_recorded_development"
    return {"evaluation_scope": "exploratory_replay", "independence": status,
            "overlapping_sessions": sorted(sessions & development),
            "overlapping_participants": sorted(subjects & participants),
            "trained_on": list(bundle.data_origins), "physical_validation": "pending",
            "caveat": "Replay exploratório não substitui holdout reservado, CV agrupada e benchmark físico."}
