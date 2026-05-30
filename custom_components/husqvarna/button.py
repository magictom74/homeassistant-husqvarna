"""Buttons for one-shot mower actions.

* Park until next schedule / further notice
* Pause / Resume schedule
* Confirm error (only meaningful while a confirmable error is active)
* Reset cutting-blade usage time (after a blade change)
* Refresh messages (pulls the alarm history)
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HusqvarnaCoordinator
from .entity import HusqvarnaMowerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HusqvarnaCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.data is None:
        return

    entities: list[ButtonEntity] = []
    for mower_id, m in coordinator.data.items():
        entities.extend([
            ParkUntilNextScheduleButton(coordinator, mower_id),
            ParkUntilFurtherNoticeButton(coordinator, mower_id),
            PauseButton(coordinator, mower_id),
            ResumeScheduleButton(coordinator, mower_id),
            RefreshMessagesButton(coordinator, mower_id),
        ])
        if m.capabilities.can_confirm_error:
            entities.append(ConfirmErrorButton(coordinator, mower_id))
    async_add_entities(entities)


class _BaseMowerButton(HusqvarnaMowerEntity, ButtonEntity):
    pass


class ParkUntilNextScheduleButton(_BaseMowerButton):
    _attr_translation_key = "park_until_next_schedule"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="park_until_next_schedule",
            translation_key="park_until_next_schedule",
        )

    async def async_press(self) -> None:
        await self.coordinator.client.park_until_next_schedule(self._mower_id)


class ParkUntilFurtherNoticeButton(_BaseMowerButton):
    _attr_translation_key = "park_until_further_notice"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="park_until_further_notice",
            translation_key="park_until_further_notice",
        )

    async def async_press(self) -> None:
        await self.coordinator.client.park_until_further_notice(self._mower_id)


class PauseButton(_BaseMowerButton):
    _attr_translation_key = "pause"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="pause",
            translation_key="pause",
        )

    async def async_press(self) -> None:
        await self.coordinator.client.pause(self._mower_id)


class ResumeScheduleButton(_BaseMowerButton):
    _attr_translation_key = "resume_schedule"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="resume_schedule",
            translation_key="resume_schedule",
        )

    async def async_press(self) -> None:
        await self.coordinator.client.resume_schedule(self._mower_id)


class ConfirmErrorButton(_BaseMowerButton):
    """Hit /errors/confirm to clear a confirmable error.

    Only exposed for mowers whose ``capabilities.can_confirm_error`` is
    true; even on those models the cloud may reject the call if the
    current error isn't actually confirmable.
    """

    _attr_translation_key = "confirm_error"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="confirm_error",
            translation_key="confirm_error",
        )

    @property
    def available(self) -> bool:
        m = self.mower
        return super().available and m is not None and m.has_error and m.error.confirmable

    async def async_press(self) -> None:
        await self.coordinator.client.confirm_error(self._mower_id)


class RefreshMessagesButton(_BaseMowerButton):
    """Pulls the cloud's mower-message history into the messages sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "refresh_messages"

    def __init__(self, coordinator: HusqvarnaCoordinator, mower_id: str) -> None:
        super().__init__(
            coordinator, mower_id,
            unique_id_suffix="refresh_messages",
            translation_key="refresh_messages",
        )

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_messages(self._mower_id)
