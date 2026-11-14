"""Independent NASA reference, UTC/DST, geometry and missing-data failures."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest
from hermes_ext.fortune_oracle import western_bridge as bridge, ephemeris
from hermes_ext.fortune_oracle.astro_input import AstroBirthInput
from hermes_ext.fortune_oracle.western_schema import WesternPlanet,TROPICAL_SIGNS


@pytest.fixture
def provisioned():
    try:
        ephemeris.resources()
    except ephemeris.EphemerisUnavailable:
        pytest.skip('Skyfield + pinned local DE440s are required for numeric ephemeris tests')


def inp(when='2000-01-01T12:00',zone='UTC',lat=0,lon=0):
    return AstroBirthInput(birth_datetime=when,timezone=zone,latitude=lat,longitude=lon)


def test_nasa_horizons_independent_reference_two_epochs_five_bodies(provisioned):
    reference = json.loads((Path(__file__).parent/'fixtures/horizons_de440_reference.json').read_text())
    for index,epoch in enumerate(reference['epochs_utc']):
        chart = bridge.calculate_western_chart(inp(epoch))
        assert chart.ok and len(chart.planets) == 10
        planets = chart.planet_dict()
        for name,record in reference['records'].items():
            difference = abs((planets[name].longitude-record['longitudes'][index]+180)%360-180)
            assert difference < 0.001, (epoch,name,difference)  # 3.6 arcseconds, distinct algorithms


def test_input_time_zones_same_instant_and_dst_are_correct(provisioned):
    utc = bridge.calculate_western_chart(inp('2024-07-01T12:00','UTC'))
    ny = bridge.calculate_western_chart(inp('2024-07-01T08:00','America/New_York'))
    seoul = bridge.calculate_western_chart(inp('2024-07-01T21:00','Asia/Seoul'))
    assert utc.ok and ny.ok and seoul.ok
    assert [p.longitude for p in utc.planets] == [p.longitude for p in ny.planets] == [p.longitude for p in seoul.planets]
    assert ephemeris.birth_utc(inp('2024-01-01T07:00','America/New_York')) == datetime(2024,1,1,12,tzinfo=timezone.utc)


@pytest.mark.parametrize('when,zone', [('2024-03-10T02:30','America/New_York'),
    ('2024-11-03T01:30','America/New_York'),('2000-01-01','UTC'),
    ('2000-02-30T12:00','UTC'),('2000-01-01T24:00','UTC'),('2000-01-01T12:00','Private/Invalid')])
def test_invalid_or_ambiguous_times_block_without_stub_or_private_error(when,zone):
    chart = bridge.calculate_western_chart(inp(when,zone))
    assert not chart.ok and chart.status == 'blocked' and not chart.planets
    assert when not in str(chart.blockers) and zone not in str(chart.blockers)


def test_missing_corrupt_kernel_or_dependency_never_uses_stub(tmp_path):
    for path in (tmp_path/'missing.bsp',tmp_path/'corrupt.bsp'):
        if path.name.startswith('corrupt'):
            path.write_bytes(b'not a JPL kernel')
        with patch.dict('os.environ',{'FORTUNE_EPHEMERIS_PATH':str(path)}):
            assert bridge.backend_info()['status'] == 'unavailable'
            chart = bridge.calculate_western_chart(inp())
            assert not chart.ok and not chart.planets
    with patch.object(ephemeris,'resources',side_effect=ephemeris.EphemerisUnavailable):
        assert not bridge.calculate_western_chart(inp()).ok


def test_no_legacy_formula_is_called(provisioned):
    with patch.object(bridge,'_sun_longitude',side_effect=AssertionError), \
         patch.object(bridge,'_moon_longitude',side_effect=AssertionError), \
         patch.object(bridge,'_planet_longitude',side_effect=AssertionError):
        assert bridge.calculate_western_chart(inp()).ok


def test_missing_location_is_partial_and_no_birth_time_is_blocked(provisioned):
    chart = bridge.calculate_western_chart(inp(lat=None,lon=None))
    assert chart.ok and chart.status == 'partial' and len(chart.planets) == 10
    assert chart.ascendant is None and chart.midheaven is None and chart.houses == []
    assert not bridge.calculate_western_chart(inp('2000-01-01')).ok


def test_retrograde_and_provenance_reach_renderer_without_raw_birth_time(provisioned):
    from hermes_ext.fortune_oracle.oracle_input import UnifiedOracleInput
    from hermes_ext.fortune_oracle.oracle_method_adapters import adapt_western
    from hermes_ext.fortune_oracle.oracle_renderer import render_final_reading
    chart = bridge.calculate_western_chart(inp())
    assert chart.planet_dict()['Saturn'].retrograde is True
    assert chart.planet_dict()['Sun'].retrograde is False
    card = adapt_western(UnifiedOracleInput(birth_datetime='2000-01-01T12:00',timezone='UTC',latitude=0,longitude=0))
    assert card.backend == 'skyfield-jpl-de440s' and card.calculation_mode == 'computed'
    assert card.facts['provenance']['sha256'] == ephemeris.KERNEL_SHA256
    assert len(card.facts['planet_positions']) == 10
    text = render_final_reading([card])
    assert 'skyfield-jpl-de440s' in text and '2000-01-01' not in text and '12:00' not in text
    assert 'DE440s' in text and ephemeris.KERNEL_SHA256 in text


@pytest.mark.parametrize('first,second,kind,orb', [(359,1,'conjunction',2),(0,180,'opposition',0),
    (0,120,'trine',0),(0,90,'square',0),(0,60,'sextile',0)])
def test_aspect_angle_uses_true_separation_and_wraparound(first,second,kind,orb):
    planets = [WesternPlanet(name=name,sign=TROPICAL_SIGNS[int(lon//30)],degree=lon%30)
               for name,lon in [('Sun',first),('Moon',second)]]
    found = bridge._detect_aspects(planets)
    assert len(found) == 1 and found[0].aspect_type == kind and found[0].orb == orb


def test_horizon_angles_are_on_ecliptic_and_correct_half_of_horizon(provisioned):
    import numpy as np
    from skyfield.framelib import ecliptic_frame
    _,t = ephemeris.positions(datetime(2000,1,1,12,tzinfo=timezone.utc))
    for lat,lon in ((0,0),(37.5665,126.978),(-33.8688,151.2093),(70,10)):
        asc,mc = ephemeris.horizon_angles(t,lat,lon)
        frame = ecliptic_frame.rotation_at(t) @ t.M.T
        lst = math.radians((t.gast*15+lon)%360)
        phi = math.radians(lat)
        up = np.array([math.cos(phi)*math.cos(lst),math.cos(phi)*math.sin(lst),math.sin(phi)])
        east = np.array([-math.sin(lst),math.cos(lst),0])
        def vector(angle):
            angle = math.radians(angle)
            return frame.T @ np.array([math.cos(angle),math.sin(angle),0])
        assert abs(float(vector(asc) @ up)) < 1e-10
        assert float(vector(asc) @ east) > 0
        assert abs(float(vector(mc) @ east)) < 1e-10
    chart = bridge.calculate_western_chart(inp(lat=90))
    assert chart.ok and chart.status == 'partial' and chart.ascendant is None


def test_house_systems_use_computed_ascendant(provisioned):
    birth = inp()
    birth.house_system_preference = 'Equal House'
    chart = bridge.calculate_western_chart(birth)
    assert chart.house_system == 'Equal House'
    assert chart.houses == [(chart.ascendant.longitude+i*30)%360 for i in range(12)]
    birth.house_system_preference = 'Whole Sign'
    whole = bridge.calculate_western_chart(birth)
    assert whole.houses[0] == math.floor(whole.ascendant.longitude/30)*30


def test_chart_calculation_never_downloads(provisioned):
    with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
        assert bridge.calculate_western_chart(inp()).ok


def test_provision_preserves_existing_file_without_network(tmp_path, monkeypatch):
    import hashlib
    from hermes_ext.fortune_oracle import ephemeris_setup as setup
    target = tmp_path / 'existing.bsp'
    target.write_bytes(b'fixture')
    monkeypatch.setattr(setup, 'KERNEL_SHA256', hashlib.sha256(b'fixture').hexdigest())
    with patch.object(setup, 'urlopen', side_effect=AssertionError('network forbidden')):
        assert setup.provision(target) == target
        target.write_bytes(b'unexpected existing bytes')
        with pytest.raises(ValueError, match='not overwritten'):
            setup.provision(target)
    assert target.read_bytes() == b'unexpected existing bytes'


def test_provision_rejects_bad_download_and_removes_temporary_file(tmp_path):
    import io
    from hermes_ext.fortune_oracle import ephemeris_setup as setup
    target = tmp_path / 'new.bsp'
    with patch.object(setup, 'urlopen', return_value=io.BytesIO(b'corrupt download')):
        with pytest.raises(ValueError, match='integrity verification'):
            setup.provision(target)
    assert list(tmp_path.iterdir()) == []


def test_provision_network_failure_removes_temporary_file(tmp_path):
    from hermes_ext.fortune_oracle import ephemeris_setup as setup
    with patch.object(setup, 'urlopen', side_effect=OSError('offline')):
        with pytest.raises(OSError, match='offline'):
            setup.provision(tmp_path / 'new.bsp')
    assert list(tmp_path.iterdir()) == []
