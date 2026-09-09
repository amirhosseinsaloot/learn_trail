"""Identifiers are UUIDv7 and time-ordered (R-24, R-28)."""

import uuid

from nuroli.shared_kernel.ids import ConversationId, UserId, new_id


def test_new_id_is_uuid_version_7() -> None:
    generated = new_id()
    assert isinstance(generated, uuid.UUID)
    assert generated.version == 7


def test_ids_generated_in_sequence_sort_in_generation_order() -> None:
    generated = [new_id() for _ in range(1000)]
    assert generated == sorted(generated)
    assert len(set(generated)) == len(generated)


def test_typed_ids_wrap_uuids_without_changing_them() -> None:
    raw = new_id()
    assert UserId(raw) == raw
    assert ConversationId(raw) == raw
