from src.crew import _parse_decomposed, _topo_sort
from src.schemas.story import TicketDraft


# --- _parse_decomposed ---


def test_parse_decomposed_from_json_array():
    output = """[
        {"title": "Epic", "type": "epic", "category": "infra", "size": "L",
         "priority": "high", "body": "...", "depends_on": []},
        {"title": "Story", "type": "story", "category": "backend", "size": "S",
         "priority": "medium", "body": "...", "depends_on": [0]}
    ]"""
    result = _parse_decomposed(output)
    assert len(result.tickets) == 2
    assert result.tickets[0].type == "epic"
    assert result.tickets[1].depends_on == [0]


def test_parse_decomposed_from_json_object():
    output = """{"tickets": [
        {"title": "Epic", "type": "epic", "category": "infra", "size": "L",
         "priority": "high", "body": "..."}
    ]}"""
    result = _parse_decomposed(output)
    assert len(result.tickets) == 1


def test_parse_decomposed_from_markdown_fenced_json():
    output = """Here is your decomposition:
```json
[{"title": "Epic", "type": "epic", "category": "infra", "size": "L",
  "priority": "high", "body": "..."}]
```"""
    result = _parse_decomposed(output)
    assert result.tickets[0].title == "Epic"


def test_parse_decomposed_returns_empty_on_garbage():
    result = _parse_decomposed("I cannot decompose this, sorry.")
    assert result.tickets == []


# --- _topo_sort ---


def _make_ticket(deps: list[int]) -> TicketDraft:
    return TicketDraft(
        title="t",
        type="story",
        category="x",
        size="S",
        priority="low",
        body="b",
        depends_on=deps,
    )


def test_topo_sort_no_deps():
    tickets = [_make_ticket([]), _make_ticket([]), _make_ticket([])]
    order = _topo_sort(tickets)
    assert sorted(order) == [0, 1, 2]  # all returned, any order is valid


def test_topo_sort_linear_chain():
    # 0 → 1 → 2 (each depends on the previous)
    tickets = [_make_ticket([]), _make_ticket([0]), _make_ticket([1])]
    order = _topo_sort(tickets)
    assert order.index(0) < order.index(1) < order.index(2)


def test_topo_sort_epic_before_stories():
    # epic at 0, stories at 1 and 2 both depending on epic
    tickets = [
        _make_ticket([]),  # epic
        _make_ticket([0]),  # story A
        _make_ticket([0]),  # story B
    ]
    order = _topo_sort(tickets)
    assert order[0] == 0  # epic is first
    assert set(order[1:]) == {1, 2}


def test_topo_sort_returns_all_indices():
    tickets = [_make_ticket([]), _make_ticket([0]), _make_ticket([1])]
    order = _topo_sort(tickets)
    assert sorted(order) == [0, 1, 2]


def test_topo_sort_handles_cycle_gracefully():
    # Malformed: 0 and 1 depend on each other — should not infinite-loop
    tickets = [_make_ticket([1]), _make_ticket([0])]
    order = _topo_sort(tickets)
    assert sorted(order) == [0, 1]  # both indices returned despite cycle
