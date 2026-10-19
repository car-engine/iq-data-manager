"""Log tab templates (DECISIONS.md D80). Files live in tmp_path."""

import tomllib

import pytest

from iqdm.entry import ChannelInput, EntryInput, ParamInput
from iqdm.models import Endianness, IqLayout, Project, SampleType, Site
from iqdm.templates import (
    FIELD_LABELS,
    LogTemplate,
    TemplateChannel,
    TemplateError,
    TemplateField,
    applied_text,
    apply_template,
    filled_fields,
    from_toml_data,
    match_name,
    read_template,
    template_from_input,
    to_toml_data,
    write_template,
)

SITES = [Site(name="Rooftop A", id=1), Site(name="Lab", id=2)]
PROJECTS = [Project(name="Radar Trial", id=7)]
ALL = set(TemplateField)


def full_form() -> EntryInput:
    return EntryInput(
        logged_by=" userA ",
        site_id=1,
        project_id=7,
        recording_plan_ref="plan-9",
        remarks="Standard USRP set-up\nsecond line",
        dtype=SampleType.INT8,
        iq_layout=IqLayout.PLANAR_IQ,
        endianness=Endianness.BIG,
        header_bytes=64,
        file_duration_s=0.5,  # from the scan: never in a template
        channels=[
            ChannelInput(channel_index=0, band="VHF", fc_mhz="145.8", fs_text="1M"),
            ChannelInput(channel_index=1, band="", fc_mhz="", fs_text="1M"),
        ],
        params=[
            ParamInput(param="SDR", value="USRP B210"),
            ParamInput(param="Antenna", value="Yagi", unit="", channel_index=0),
            ParamInput(),  # blank rows are left out
        ],
    )


def full_template() -> LogTemplate:
    return template_from_input(full_form(), ALL, site_name="Rooftop A", project_name="Radar Trial")


def test_a_template_holds_the_typed_fields_and_nothing_from_the_scan():
    tpl = full_template()
    assert tpl.fields() == list(TemplateField)
    assert tpl.logged_by == "userA"
    assert (tpl.site, tpl.project) == ("Rooftop A", "Radar Trial")
    assert (tpl.sample_type, tpl.iq_layout, tpl.endianness, tpl.header_bytes) == (
        SampleType.INT8,
        IqLayout.PLANAR_IQ,
        Endianness.BIG,
        64,
    )
    assert tpl.channels == (TemplateChannel(index=0, band="VHF", fc_mhz="145.8"),)
    assert [p.param for p in tpl.rf_chain] == ["SDR", "Antenna"]
    data = to_toml_data(tpl)
    assert not {"fs", "fs_text", "file_duration_s", "start", "storage_root"} & set(data)
    assert set(data["channels"][0]) == {"index", "band", "fc_mhz"}


def test_round_trip_through_a_file(tmp_path):
    path = tmp_path / "usrp.toml"
    write_template(path, full_template())
    assert read_template(path) == full_template()
    assert not (tmp_path / "usrp.toml.new").exists()


@pytest.mark.parametrize("field", list(TemplateField))
def test_each_field_alone(tmp_path, field):
    tpl = template_from_input(
        full_form(), {field}, site_name="Rooftop A", project_name="Radar Trial"
    )
    assert tpl.fields() == [field]
    path = tmp_path / f"{field}.toml"
    write_template(path, tpl)
    assert read_template(path) == tpl


def test_only_the_chosen_fields_are_written(tmp_path):
    path = tmp_path / "rf.toml"
    tpl = template_from_input(
        full_form(),
        {TemplateField.RF_CHAIN, TemplateField.SITE},
        site_name="Rooftop A",
        project_name="",
    )
    write_template(path, tpl)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"format_version", "site", "rf_chain"}
    assert data["rf_chain"][0] == {
        "applies_to": "recording",
        "param": "SDR",
        "value": "USRP B210",
        "unit": "",
    }
    assert data["rf_chain"][1]["applies_to"] == 0


def test_no_project_is_saved_as_empty_text():
    tpl = template_from_input(full_form(), {TemplateField.PROJECT}, site_name="", project_name="")
    assert tpl.project == ""
    form = EntryInput(project_id=7)
    assert apply_template(form, tpl, SITES, PROJECTS).form.project_id is None


def test_a_site_ticked_without_a_choice_is_not_written():
    tpl = template_from_input(
        full_form(), {TemplateField.SITE, TemplateField.LOGGED_BY}, site_name="", project_name=""
    )
    assert tpl.fields() == [TemplateField.LOGGED_BY]


def test_kept_channel_values_are_saved_before_a_scan():
    """D79: band and fc wait by channel number until the scan shows the rows."""
    carried = {2: ChannelInput(channel_index=2, band="UHF", fc_mhz="435")}
    tpl = template_from_input(
        EntryInput(), {TemplateField.CHANNELS}, site_name="", project_name="", carried=carried
    )
    assert tpl.channels == (TemplateChannel(index=2, band="UHF", fc_mhz="435"),)


def test_filled_fields_leave_empty_ones_out():
    form = EntryInput(logged_by="userA")
    assert filled_fields(form, "", "") == {TemplateField.LOGGED_BY, TemplateField.FORMAT}
    assert filled_fields(full_form(), "Rooftop A", "Radar Trial") == ALL


def test_import_changes_only_the_fields_the_template_holds():
    form = full_form()
    tpl = LogTemplate(remarks="new remarks", header_bytes=0)
    applied = apply_template(form, tpl, SITES, PROJECTS)
    assert applied.form.remarks == "new remarks"
    assert applied.form.header_bytes == 0
    assert applied.form.dtype == SampleType.INT8
    assert applied.form.logged_by == form.logged_by
    assert applied.form.params == form.params
    assert applied.notes == ()


def test_import_sets_channels_by_number_and_replaces_the_rf_chain():
    tpl = LogTemplate(
        channels=(
            TemplateChannel(index=1, band="UHF", fc_mhz="435"),
            TemplateChannel(index=5, band="L", fc_mhz="1575.42"),
        ),
        rf_chain=(ParamInput(param="LNA", value="20", unit="dB"),),
    )
    applied = apply_template(full_form(), tpl, SITES, PROJECTS)
    assert [(c.channel_index, c.band, c.fc_mhz, c.fs_text) for c in applied.form.channels] == [
        (0, "VHF", "145.8", "1M"),  # not in the template: unchanged
        (1, "UHF", "435", "1M"),  # fs stays
    ]
    assert set(applied.channels) == {1, 5}  # channel 5 waits for a scan that shows it
    assert [p.param for p in applied.form.params] == ["LNA"]


def test_site_and_project_match_by_name_without_letter_case():
    tpl = LogTemplate(site="lab", project="RADAR trial")
    applied = apply_template(EntryInput(), tpl, SITES, PROJECTS)
    assert (applied.form.site_id, applied.form.project_id) == (2, 7)
    assert match_name("ROOFTOP a", SITES) == SITES[0]
    assert match_name("Roof", SITES) is None


def test_a_name_the_catalogue_lacks_is_named_and_changes_nothing():
    tpl = LogTemplate(site="Hilltop", project="Survey")
    applied = apply_template(EntryInput(site_id=1, project_id=7), tpl, SITES, PROJECTS)
    assert (applied.form.site_id, applied.form.project_id) == (1, 7)
    assert applied.notes == (
        "Site 'Hilltop' is not in the catalogue. Choose it or add it.",
        "Project 'Survey' is not in the catalogue. Choose it or add it.",
    )
    assert applied_text(tpl, applied.notes) == (
        "Template loaded: site, project. " + " ".join(applied.notes)
    )


def test_applied_text_names_the_fields_in_form_order():
    assert applied_text(full_template(), ()) == (
        "Template loaded: "
        + ", ".join(FIELD_LABELS[f].lower() for f in TemplateField)
        + "."
    )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"site": "Lab"}, "not a template from this program"),
        ({"format_version": 2, "site": "Lab"}, "newer version"),
        ({"format_version": 1}, "holds no fields"),
        ({"format_version": 1, "colour": "red"}, "Unknown entry in the template: colour"),
        ({"format_version": 1, "sample_type": "int12"}, "must be one of: int8, int16, float32"),
        ({"format_version": 1, "header_bytes": -1}, "whole number, 0 or more"),
        ({"format_version": 1, "header_bytes": True}, "whole number, 0 or more"),
        ({"format_version": 1, "site": 5}, "'site' in the template must be text"),
        ({"format_version": 1, "channels": "VHF"}, "must be a list of entries"),
        ({"format_version": 1, "channels": [{"band": "VHF"}]}, "needs 'index'"),
        (
            {"format_version": 1, "channels": [{"index": 0}, {"index": 0}]},
            "lists channel 0 twice",
        ),
        ({"format_version": 1, "channels": [{"index": 0, "gain": 3}]}, "channel 1"),
        (
            {"format_version": 1, "rf_chain": [{"param": "SDR", "applies_to": "all"}]},
            "'applies_to' must be 'recording' or a channel number",
        ),
        ({"format_version": 1, "rf_chain": [{"param": "SDR", "colour": 1}]}, "RF chain row 1"),
    ],
)
def test_a_wrong_template_is_refused_with_a_plain_message(data, message):
    with pytest.raises(TemplateError, match=message):
        from_toml_data(data)


def test_numbers_are_read_as_text():
    tpl = from_toml_data(
        {
            "format_version": 1,
            "channels": [{"index": 0, "fc_mhz": 145.8}],
            "rf_chain": [{"param": "Gain", "value": 20}],
        }
    )
    assert tpl.channels[0].fc_mhz == "145.8"
    assert tpl.rf_chain[0].value == "20"
    assert tpl.rf_chain[0].channel_index is None  # applies_to defaults to the recording


def test_an_empty_rf_chain_list_clears_the_rows():
    tpl = from_toml_data({"format_version": 1, "rf_chain": []})
    assert apply_template(full_form(), tpl, SITES, PROJECTS).form.params == []


def test_a_damaged_or_missing_file_is_refused(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("format_version = = 1", encoding="utf-8")
    with pytest.raises(TemplateError, match="damaged"):
        read_template(bad)
    with pytest.raises(TemplateError, match="Cannot read"):
        read_template(tmp_path / "missing.toml")


def test_export_replaces_an_existing_template(tmp_path):
    path = tmp_path / "usrp.toml"
    write_template(path, LogTemplate(site="Lab"))
    write_template(path, LogTemplate(site="Rooftop A"))
    assert read_template(path) == LogTemplate(site="Rooftop A")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["usrp.toml"]


def test_an_empty_template_is_not_written(tmp_path):
    with pytest.raises(TemplateError, match="at least one field"):
        write_template(tmp_path / "empty.toml", LogTemplate())
    assert list(tmp_path.iterdir()) == []
