"""Kalendář jídelníčku z Job Abacus Pro."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import JobAbacusConfigEntry, JobAbacusCoordinator
from .parser import LunchDay


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JobAbacusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Vytvoří kalendářovou entitu jídelníčku."""
    async_add_entities([JobAbacusLunchCalendar(entry.runtime_data, entry)])


def _to_event(lunch: LunchDay) -> CalendarEvent:
    """Převede den jídelníčku na celodenní událost."""
    return CalendarEvent(
        summary=lunch.summary,
        start=lunch.day,
        end=lunch.day + timedelta(days=1),
        description=lunch.description,
        uid=lunch.uid,
    )


class JobAbacusLunchCalendar(
    CoordinatorEntity[JobAbacusCoordinator], CalendarEntity
):
    """Kalendář s jedním celodenním záznamem na každý den jídelníčku."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "lunch"
    _attr_icon = "mdi:food"

    def __init__(
        self, coordinator: JobAbacusCoordinator, entry: JobAbacusConfigEntry
    ) -> None:
        """Inicializuje entitu."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_lunch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=entry.title,
            configuration_url=coordinator.client.base_url,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Vrátí dnešní nebo nejbližší příští oběd."""
        today = dt_util.now().date()
        for lunch in self.coordinator.data or []:
            if lunch.day >= today:
                return _to_event(lunch)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Vrátí dny jídelníčku, které zasahují do požadovaného rozsahu."""
        events = []
        for lunch in self.coordinator.data or []:
            # Celodenní záznam dne D zabírá lokální interval [D, D+1).
            day_start = dt_util.start_of_local_day(lunch.day)
            day_end = dt_util.start_of_local_day(lunch.day + timedelta(days=1))
            if day_end > start_date and day_start < end_date:
                events.append(_to_event(lunch))
        return events
