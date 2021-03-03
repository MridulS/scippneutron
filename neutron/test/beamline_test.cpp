// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
#include <gtest/gtest.h>

#include <scipp/dataset/dataset.h>
#include <scipp/variable/operations.h>

#include "scipp/neutron/beamline.h"

using namespace scipp;
using namespace scipp::variable;
using namespace scipp::neutron;

namespace {
static const auto source_pos = Eigen::Vector3d{0.0, 0.0, -9.99};
static const auto sample_pos = Eigen::Vector3d{0.0, 0.0, 0.01};
} // namespace

Dataset makeDatasetWithBeamline() {
  Dataset beamline;
  Dataset components;
  // Source and sample
  components.setData("position", makeVariable<Eigen::Vector3d>(
                                     Dims{Dim::Row}, Shape{2}, units::m,
                                     Values{source_pos, sample_pos}));
  beamline.setCoord(Dim("source_position"), makeVariable<Eigen::Vector3d>(
                                                units::m, Values{source_pos}));
  beamline.setCoord(Dim("sample_position"), makeVariable<Eigen::Vector3d>(
                                                units::m, Values{sample_pos}));
  // TODO Need fuzzy comparison for variables to write a convenient test with
  // detectors away from the axes.
  beamline.setCoord(
      Dim("position"),
      makeVariable<Eigen::Vector3d>(Dims{Dim::Spectrum}, Shape{2}, units::m,
                                    Values{Eigen::Vector3d{1.0, 0.0, 0.01},
                                           Eigen::Vector3d{0.0, 1.0, 0.01}}));
  return beamline;
}

class BeamlineTest : public ::testing::Test {
protected:
  const Dataset dataset{makeDatasetWithBeamline()};
};

TEST_F(BeamlineTest, basics) {
  ASSERT_EQ(source_position(dataset.meta()),
            makeVariable<Eigen::Vector3d>(Dims(), Shape(), units::m,
                                          Values{source_pos}));
  ASSERT_EQ(sample_position(dataset.meta()),
            makeVariable<Eigen::Vector3d>(Dims(), Shape(), units::m,
                                          Values{sample_pos}));
  ASSERT_EQ(l1(dataset.meta()),
            makeVariable<double>(Dims(), Shape(), units::m, Values{10.0}));
}

TEST_F(BeamlineTest, l2) {
  ASSERT_EQ(l2(dataset.meta()),
            makeVariable<double>(Dims{Dim::Spectrum}, Shape{2}, units::m,
                                 Values{1.0, 1.0}));
}

TEST_F(BeamlineTest, flight_path_length) {
  ASSERT_EQ(flight_path_length(dataset.meta()),
            l1(dataset.meta()) + l2(dataset.meta()));
}

template <class T> constexpr T pi = T(3.1415926535897932385L);

TEST_F(BeamlineTest, scattering_angle) {
  ASSERT_EQ(two_theta(dataset.meta()),
            makeVariable<double>(Dims{Dim::Spectrum}, Shape{2}, units::rad,
                                 Values{pi<double> / 2, pi<double> / 2}));
  ASSERT_EQ(scattering_angle(dataset.meta()),
            0.5 * units::one * two_theta(dataset.meta()));
}

TEST_F(BeamlineTest, no_sample) {
  Dataset d(dataset);
  d.coords().erase(Dim("sample_position"));
  ASSERT_THROW(l1(d.meta()), except::NotFoundError);
  ASSERT_THROW(l2(d.meta()), except::NotFoundError);
  ASSERT_THROW(scattering_angle(d.meta()), except::NotFoundError);
  ASSERT_EQ(flight_path_length(d.meta()),
            makeVariable<double>(
                Dims{Dim::Spectrum}, Shape{2}, units::m,
                Values{(Eigen::Vector3d{1.0, 0.0, 0.01} - source_pos).norm(),
                       (Eigen::Vector3d{0.0, 1.0, 0.01} - source_pos).norm()}));
}
