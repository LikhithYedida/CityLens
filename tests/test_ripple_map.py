"""Offline tests for the Ripple Map's spatial math, using made-up metros."""
import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from analysis import ripple_map as rm
from pipeline import geo_shapes
from pipeline.utils import SourceError


def test_distance_known_pair():
    # Detroit to Chicago is about 238 miles in a straight line
    d = rm.distance_miles(np.array([42.33, 41.88]), np.array([-83.05, -87.63]))
    assert d[0, 1] == pytest.approx(238, abs=5)
    assert np.isinf(d[0, 0])


def test_ring_average_weights_and_excludes_self():
    dist = np.array([[np.inf, 50, 100], [50, np.inf, 60], [100, 60, np.inf]])
    vals = np.array([1.0, 2.0, 4.0])
    pop = np.array([1.0, 1.0, 3.0])
    near = rm.ring_average(vals, dist, pop, 0, 75)
    assert near[0] == pytest.approx(2.0)                     # only metro 1 is within 75 miles of metro 0
    assert near[1] == pytest.approx((1 * 1 + 4 * 3) / 4)     # population-weighted
    assert np.isnan(rm.ring_average(vals, dist, pop, 200, 300)[0])


def test_knn_weights_row_standardized():
    rng = np.random.default_rng(0)
    pts = rng.uniform(0, 10, (20, 2))
    dist = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
    np.fill_diagonal(dist, np.inf)
    w = rm.knn_weights(dist, k=4)
    assert np.allclose(w.sum(axis=1), 1)
    assert (np.diag(w) == 0).all()


def grid_world(clustered: bool, seed=1):
    """A 10x10 grid of metros; clustered = smooth east-west gradient, else random."""
    rng = np.random.default_rng(seed)
    xs, ys = np.meshgrid(np.arange(10), np.arange(10))
    x = xs.ravel() + (0 if clustered else 0)
    vals = x + rng.normal(0, 0.3, x.size) if clustered else rng.normal(0, 1, x.size)
    dist = np.sqrt((xs.ravel()[:, None] - xs.ravel()[None]) ** 2 + (ys.ravel()[:, None] - ys.ravel()[None]) ** 2)
    np.fill_diagonal(dist, np.inf)
    return vals, rm.knn_weights(dist, k=4)


def test_morans_i_detects_clustering_and_not_noise():
    vals, w = grid_world(clustered=True)
    assert rm.morans_i(vals, w, n_perm=199)["p_value"] < 0.01
    noise, w2 = grid_world(clustered=False)
    assert rm.morans_i(noise, w2, n_perm=199)["p_value"] > 0.05


def test_lisa_finds_hot_and_cold_edges():
    vals, w = grid_world(clustered=True)
    out = rm.lisa(vals, w, n_perm=199)
    assert {"HH", "LL"} <= set(out["cluster"])
    assert out.loc[np.argmax(vals), "cluster"] == "HH"


def test_albers_center_and_orientation():
    x0, y0 = rm.albers(37.5, -96.0)
    assert abs(float(x0)) < 1e-9 and abs(float(y0)) < 1e-9
    x_east, _ = rm.albers(37.5, -80.0)
    _, y_north = rm.albers(45.0, -96.0)
    assert x_east > 0 and y_north > 0


def test_build_panel_relative_to_national():
    dates = pd.date_range("2015-01-01", "2018-12-01", freq="MS")
    t = np.arange(len(dates))
    values = pd.DataFrame({"A": 100 * np.exp(0.01 * t), "B": 100 * np.exp(0.002 * t), "C": 100 * np.exp(0.006 * t)},
                          index=dates)
    meta = pd.DataFrame({"cbsa_code": ["A", "B", "C"], "lat": [40.0, 40.3, 45.0], "lon": [-90.0, -90.3, -80.0],
                         "population": [1e6, 2e5, 5e5]})
    p = rm.build_panel(values, meta)
    assert set(p["date"].dt.month) <= {3, 6, 9, 12}
    assert p.groupby("date")["own"].mean().abs().max() < 1e-12
    a = p[(p["cbsa_code"] == "A")].iloc[0]
    b_own = p[(p["cbsa_code"] == "B") & (p["date"] == a["date"])]["own"].iloc[0]
    assert a["ring_0_75"] == pytest.approx(b_own)            # B is ~26 miles from A; C is far away


def test_gazetteer_parse_and_validation():
    txt = ("CSAFP\tGEOID\tNAME\tCBSA_TYPE\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG          \n"
           "\t19820\tDetroit-Warren-Dearborn, MI Metro Area\t1\t1\t1\t1\t1\t42.72\t-83.23         \n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("gaz.txt", txt)
    out = geo_shapes.parse_gazetteer(buf.getvalue())
    assert out.iloc[0]["cbsa_code"] == "19820" and out.iloc[0]["lon"] == pytest.approx(-83.23)
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("gaz.txt", txt.replace("42.72", "-42.72"))
    with pytest.raises(SourceError):
        geo_shapes.parse_gazetteer(bad.getvalue())
