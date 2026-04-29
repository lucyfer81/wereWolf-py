from src.llm import create_player_agent, create_gm_agent, PlayerResponse, GMSummary


def test_player_response_model():
    resp = PlayerResponse(
        action="speech",
        target="Seat3",
        content="我怀疑Seat3的发言前后矛盾",
        confidence="high",
        risk_if_wrong="投错可能误杀村民",
        alt_target="Seat5",
        target_vs_alt_reason="Seat3的矛盾比Seat5更明显",
        evidence=["Seat3在Day1说观察Seat5，Day2又投了Seat7"],
        changed_vote=False,
        why_change="",
    )
    assert resp.action == "speech"
    assert resp.target == "Seat3"
    assert resp.confidence == "high"


def test_player_response_defaults():
    resp = PlayerResponse(
        action="vote", target="Seat1", content="观望", confidence="low"
    )
    assert resp.risk_if_wrong == ""
    assert resp.changed_vote is False
    assert resp.evidence == []


def test_gm_summary_model():
    summary = GMSummary(summary="Day1摘要...")
    assert summary.summary == "Day1摘要..."


def test_create_player_agent():
    agent = create_player_agent()
    assert agent is not None


def test_create_gm_agent():
    agent = create_gm_agent()
    assert agent is not None
