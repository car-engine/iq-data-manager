"""Log tab templates: the typed fields of an entry saved to a TOML file (DECISIONS.md D80).

A template can hold any field the user types in the Log tab: logged by, site, project,
plan reference, remarks, the file format, band and fc per channel number, and the RF
chain rows. It never holds a value from the scan: start and end, file counts, fs, file
duration or the folder. Every field is optional. Import changes only the fields the
file holds.

Site and project are stored by name, because ids differ between catalogues. An empty
project means "no project". No Qt here.
"""

import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import tomli_w

from iqdm.entry import ChannelInput, EntryInput, ParamInput
from iqdm.models import Endianness, IqLayout, Project, SampleType, Site

FORMAT_VERSION = 1
FILE_SUFFIX = ".toml"
NEW_SUFFIX = ".new"
RECORDING_SCOPE = "recording"  # applies_to of an RF chain row for the whole recording


class TemplateError(ValueError):
    """A template file that cannot be read or written. The text is for the user."""


class TemplateField(StrEnum):
    """The groups the user chooses on export, in the order of the form."""

    LOGGED_BY = "logged_by"
    SITE = "site"
    PROJECT = "project"
    PLAN = "recording_plan_ref"
    REMARKS = "remarks"
    FORMAT = "format"
    CHANNELS = "channels"
    RF_CHAIN = "rf_chain"


FIELD_LABELS: dict[TemplateField, str] = {
    TemplateField.LOGGED_BY: "Logged by",
    TemplateField.SITE: "Site",
    TemplateField.PROJECT: "Project",
    TemplateField.PLAN: "Recording plan reference",
    TemplateField.REMARKS: "Remarks",
    TemplateField.FORMAT: "File format",
    TemplateField.CHANNELS: "Band and fc of each channel",
    TemplateField.RF_CHAIN: "RF chain",
}

_FORMAT_KEYS = ("sample_type", "iq_layout", "endianness", "header_bytes")
_TOP_KEYS = frozenset(
    {"format_version", "logged_by", "site", "project", "recording_plan_ref", "remarks"}
    | set(_FORMAT_KEYS)
    | {"channels", "rf_chain"}
)
_CHANNEL_KEYS = frozenset({"index", "band", "fc_mhz"})
_RF_KEYS = frozenset({"applies_to", "param", "value", "unit"})


@dataclass(frozen=True)
class TemplateChannel:
    index: int
    band: str = ""
    fc_mhz: str = ""


@dataclass(frozen=True, kw_only=True)
class LogTemplate:
    """The fields of a template. None means the template does not hold that field."""

    logged_by: str | None = None
    site: str | None = None
    project: str | None = None  # "" means no project
    recording_plan_ref: str | None = None
    remarks: str | None = None
    sample_type: SampleType | None = None
    iq_layout: IqLayout | None = None
    endianness: Endianness | None = None
    header_bytes: int | None = None
    channels: tuple[TemplateChannel, ...] | None = None
    rf_chain: tuple[ParamInput, ...] | None = None

    def fields(self) -> list[TemplateField]:
        """The groups this template holds, in the order of the form."""
        present = {
            TemplateField.LOGGED_BY: self.logged_by is not None,
            TemplateField.SITE: self.site is not None,
            TemplateField.PROJECT: self.project is not None,
            TemplateField.PLAN: self.recording_plan_ref is not None,
            TemplateField.REMARKS: self.remarks is not None,
            TemplateField.FORMAT: any(
                v is not None
                for v in (self.sample_type, self.iq_layout, self.endianness, self.header_bytes)
            ),
            TemplateField.CHANNELS: self.channels is not None,
            TemplateField.RF_CHAIN: self.rf_chain is not None,
        }
        return [f for f in TemplateField if present[f]]


# ---------------------------------------------------------------------------
# From the form, and back
# ---------------------------------------------------------------------------


def filled_fields(form: EntryInput, site_name: str, project_name: str) -> set[TemplateField]:
    """The groups that hold something in the form. Export ticks these at first."""
    filled = {
        TemplateField.LOGGED_BY: bool(form.logged_by.strip()),
        TemplateField.SITE: bool(site_name.strip()),
        TemplateField.PROJECT: bool(project_name.strip()),
        TemplateField.PLAN: bool(form.recording_plan_ref.strip()),
        TemplateField.REMARKS: bool(form.remarks.strip()),
        TemplateField.FORMAT: True,
        TemplateField.CHANNELS: bool(_channels_of(form)),
        TemplateField.RF_CHAIN: bool(_rows_of(form)),
    }
    return {f for f, ok in filled.items() if ok}


def template_from_input(
    form: EntryInput,
    fields: Iterable[TemplateField],
    *,
    site_name: str,
    project_name: str,
    carried: Mapping[int, ChannelInput] | None = None,
) -> LogTemplate:
    """A template of the chosen fields of the form.

    site_name is the chosen site's name, or "" for none; project_name is "" for no
    project. carried holds band and fc kept for channels the form does not show yet
    (D79); the form's own rows replace them.
    """
    chosen = set(fields)
    tpl = LogTemplate()
    if TemplateField.LOGGED_BY in chosen:
        tpl = replace(tpl, logged_by=form.logged_by.strip())
    if TemplateField.SITE in chosen and site_name.strip():
        tpl = replace(tpl, site=site_name.strip())
    if TemplateField.PROJECT in chosen:
        tpl = replace(tpl, project=project_name.strip())
    if TemplateField.PLAN in chosen:
        tpl = replace(tpl, recording_plan_ref=form.recording_plan_ref.strip())
    if TemplateField.REMARKS in chosen:
        tpl = replace(tpl, remarks=form.remarks.strip())
    if TemplateField.FORMAT in chosen:
        tpl = replace(
            tpl,
            sample_type=SampleType(form.dtype),
            iq_layout=IqLayout(form.iq_layout),
            endianness=Endianness(form.endianness),
            header_bytes=int(form.header_bytes),
        )
    if TemplateField.CHANNELS in chosen:
        tpl = replace(tpl, channels=_channels_of(form, carried))
    if TemplateField.RF_CHAIN in chosen:
        tpl = replace(tpl, rf_chain=_rows_of(form))
    return tpl


def _channels_of(
    form: EntryInput, carried: Mapping[int, ChannelInput] | None = None
) -> tuple[TemplateChannel, ...]:
    merged = {**(carried or {}), **{c.channel_index: c for c in form.channels}}
    return tuple(
        TemplateChannel(index=i, band=c.band.strip(), fc_mhz=c.fc_mhz.strip())
        for i, c in sorted(merged.items())
        if c.band.strip() or c.fc_mhz.strip()
    )


def _rows_of(form: EntryInput) -> tuple[ParamInput, ...]:
    return tuple(
        ParamInput(
            channel_index=p.channel_index,
            param=p.param.strip(),
            value=p.value.strip(),
            unit=p.unit.strip(),
        )
        for p in form.params
        if not p.is_blank
    )


def match_name[T: (Site, Project)](name: str, items: Sequence[T]) -> T | None:
    """The entry whose name equals `name` without letter case, as the database compares."""
    wanted = name.strip().casefold()
    return next((i for i in items if i.name.casefold() == wanted), None)


@dataclass(frozen=True)
class Applied:
    """The form after an import, the channel values for later rows, and notes."""

    form: EntryInput
    channels: dict[int, ChannelInput]  # band and fc by channel number, all of the template
    notes: tuple[str, ...]  # names the catalogue does not hold


def apply_template(
    form: EntryInput, tpl: LogTemplate, sites: Sequence[Site], projects: Sequence[Project]
) -> Applied:
    """The form with the template's fields in place. Fields it does not hold stay.

    A site or project name the catalogue does not hold leaves that field as it was and
    gives a note. Band and fc go to the form's rows of the same channel number, and
    all of them are returned for rows a later scan shows (D79).
    """
    notes: list[str] = []
    out = form
    if tpl.logged_by is not None:
        out = replace(out, logged_by=tpl.logged_by)
    if tpl.site is not None:
        site = match_name(tpl.site, sites)
        if site is None:
            notes.append(f"Site '{tpl.site}' is not in the catalogue. Choose it or add it.")
        else:
            out = replace(out, site_id=site.id)
    if tpl.project is not None:
        if not tpl.project:
            out = replace(out, project_id=None)
        elif (project := match_name(tpl.project, projects)) is None:
            notes.append(f"Project '{tpl.project}' is not in the catalogue. Choose it or add it.")
        else:
            out = replace(out, project_id=project.id)
    if tpl.recording_plan_ref is not None:
        out = replace(out, recording_plan_ref=tpl.recording_plan_ref)
    if tpl.remarks is not None:
        out = replace(out, remarks=tpl.remarks)
    if tpl.sample_type is not None:
        out = replace(out, dtype=tpl.sample_type)
    if tpl.iq_layout is not None:
        out = replace(out, iq_layout=tpl.iq_layout)
    if tpl.endianness is not None:
        out = replace(out, endianness=tpl.endianness)
    if tpl.header_bytes is not None:
        out = replace(out, header_bytes=tpl.header_bytes)
    channels: dict[int, ChannelInput] = {}
    if tpl.channels is not None:
        channels = {
            c.index: ChannelInput(channel_index=c.index, band=c.band, fc_mhz=c.fc_mhz)
            for c in tpl.channels
        }
        out = replace(
            out,
            channels=[
                replace(
                    c, band=channels[c.channel_index].band, fc_mhz=channels[c.channel_index].fc_mhz
                )
                if c.channel_index in channels
                else c
                for c in out.channels
            ],
        )
    if tpl.rf_chain is not None:
        out = replace(out, params=list(tpl.rf_chain))
    return Applied(form=out, channels=channels, notes=tuple(notes))


def applied_text(tpl: LogTemplate, notes: Sequence[str]) -> str:
    """The message line after an import. The labels keep their case, as in "RF chain"."""
    names = ", ".join(FIELD_LABELS[f] for f in tpl.fields())
    text = f"Template loaded: {names}."
    return " ".join([text, *notes])


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def to_toml_data(tpl: LogTemplate) -> dict[str, Any]:
    data: dict[str, Any] = {"format_version": FORMAT_VERSION}
    for key in ("logged_by", "site", "project", "recording_plan_ref", "remarks"):
        value = getattr(tpl, key)
        if value is not None:
            data[key] = value
    if tpl.sample_type is not None:
        data["sample_type"] = str(tpl.sample_type)
    if tpl.iq_layout is not None:
        data["iq_layout"] = str(tpl.iq_layout)
    if tpl.endianness is not None:
        data["endianness"] = str(tpl.endianness)
    if tpl.header_bytes is not None:
        data["header_bytes"] = tpl.header_bytes
    if tpl.channels is not None:
        data["channels"] = [
            {"index": c.index, "band": c.band, "fc_mhz": c.fc_mhz} for c in tpl.channels
        ]
    if tpl.rf_chain is not None:
        data["rf_chain"] = [
            {
                "applies_to": RECORDING_SCOPE if p.channel_index is None else p.channel_index,
                "param": p.param,
                "value": p.value,
                "unit": p.unit,
            }
            for p in tpl.rf_chain
        ]
    return data


def from_toml_data(data: Mapping[str, Any]) -> LogTemplate:
    """Check the parsed TOML of a template. Raises TemplateError with plain text."""
    version = data.get("format_version")
    if version != FORMAT_VERSION:  # first, so another TOML file is not listed key by key
        raise TemplateError(
            "This is not a template from this program, or it is from a newer version."
        )
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise TemplateError(f"Unknown entry in the template: {', '.join(unknown)}.")
    tpl = LogTemplate(
        logged_by=_text(data, "logged_by"),
        site=_text(data, "site"),
        project=_text(data, "project"),
        recording_plan_ref=_text(data, "recording_plan_ref"),
        remarks=_text(data, "remarks"),
        sample_type=_choice(data, "sample_type", SampleType),
        iq_layout=_choice(data, "iq_layout", IqLayout),
        endianness=_choice(data, "endianness", Endianness),
        header_bytes=_header(data),
        channels=_channels(data),
        rf_chain=_rf_chain(data),
    )
    if not tpl.fields():
        raise TemplateError("The template holds no fields.")
    return tpl


def _text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TemplateError(f"'{key}' in the template must be text.")
    return value


def _choice[E: StrEnum](data: Mapping[str, Any], key: str, kind: type[E]) -> E | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(str(e) for e in kind)
        raise TemplateError(f"'{key}' in the template must be one of: {allowed}.") from None


def _whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _header(data: Mapping[str, Any]) -> int | None:
    value = data.get("header_bytes")
    if value is None:
        return None
    if not _whole_number(value):
        raise TemplateError("'header_bytes' in the template must be a whole number, 0 or more.")
    return int(value)


def _table_list(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise TemplateError(f"'{key}' in the template must be a list of entries.")
    return value


def _number_text(value: object, what: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    raise TemplateError(f"{what} in the template must be a number or text.")


def _channels(data: Mapping[str, Any]) -> tuple[TemplateChannel, ...] | None:
    rows = _table_list(data, "channels")
    if rows is None:
        return None
    seen: set[int] = set()
    out = []
    for n, row in enumerate(rows, start=1):
        unknown = sorted(set(row) - _CHANNEL_KEYS)
        if unknown:
            raise TemplateError(
                f"Unknown entry in channel {n} of the template: {', '.join(unknown)}."
            )
        index = row.get("index")
        if not _whole_number(index):
            raise TemplateError(
                f"Channel {n} of the template needs 'index', a whole number, 0 or more."
            )
        if index in seen:
            raise TemplateError(f"The template lists channel {index} twice.")
        seen.add(index)
        band = row.get("band", "")
        if not isinstance(band, str):
            raise TemplateError(f"The band of channel {index} in the template must be text.")
        fc = _number_text(row.get("fc_mhz", ""), f"The fc of channel {index}")
        out.append(TemplateChannel(index=index, band=band, fc_mhz=fc))
    return tuple(out)


def _rf_chain(data: Mapping[str, Any]) -> tuple[ParamInput, ...] | None:
    rows = _table_list(data, "rf_chain")
    if rows is None:
        return None
    out = []
    for n, row in enumerate(rows, start=1):
        unknown = sorted(set(row) - _RF_KEYS)
        if unknown:
            raise TemplateError(
                f"Unknown entry in RF chain row {n} of the template: {', '.join(unknown)}."
            )
        scope = row.get("applies_to", RECORDING_SCOPE)
        if scope != RECORDING_SCOPE and not _whole_number(scope):
            raise TemplateError(
                f"RF chain row {n} of the template: 'applies_to' must be "
                f"'{RECORDING_SCOPE}' or a channel number."
            )
        fields = {}
        for key in ("param", "value", "unit"):
            value = row.get(key, "")
            fields[key] = _number_text(value, f"'{key}' of RF chain row {n}")
        out.append(ParamInput(channel_index=None if scope == RECORDING_SCOPE else scope, **fields))
    return tuple(out)


def read_template(path: Path) -> LogTemplate:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TemplateError(f"Cannot read the template file: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TemplateError(f"The template file is damaged: {exc}") from exc
    return from_toml_data(data)


def write_template(path: Path, tpl: LogTemplate) -> None:
    """Write the template to `path`, replacing a file the user chose to replace.

    The text is read back before anything is written. It goes to `<name>.new` in the
    same folder, which then replaces `path`. A failure before that last step leaves an
    existing file at `path` unchanged.
    """
    if not tpl.fields():
        raise TemplateError("Choose at least one field to save.")
    text = tomli_w.dumps(to_toml_data(tpl))
    if from_toml_data(tomllib.loads(text)) != tpl:
        raise TemplateError("The template does not read back the same. Nothing was saved.")
    new_path = path.with_name(path.name + NEW_SUFFIX)
    try:
        new_path.write_text(text, encoding="utf-8")
        new_path.replace(path)
    except OSError as exc:
        raise TemplateError(f"Cannot save the template file: {exc}") from exc
