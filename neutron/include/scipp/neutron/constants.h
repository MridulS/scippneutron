// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
/// @file
/// @author Simon Heybrock
#pragma once

#include <tuple>

#include <units/units.hpp>

#include <scipp/common/constants.h>

#include <scipp/units/unit.h>

#include <scipp/variable/operations.h>

#include <scipp/neutron/beamline.h>

namespace scipp::neutron::constants {

constexpr auto tof_to_s =
    1e-6 * llnl::units::precise::second /
    (llnl::units::precise::micro * llnl::units::precise::second);
constexpr auto J_to_meV =
    1e3 / llnl::units::constants::e.value() * llnl::units::precise::milli *
    llnl::units::precise::energy::eV / llnl::units::precise::J;
constexpr auto m_to_angstrom = 1e10 * llnl::units::precise::distance::angstrom /
                               llnl::units::precise::meter;

// In tof-to-energy conversions we *divide* by time-of-flight (squared), so the
// tof_to_s factor is in the denominator.
constexpr auto tof_to_energy_physical_constants =
    0.5 * llnl::units::constants::mn * J_to_meV / (tof_to_s * tof_to_s);

constexpr auto tof_to_dspacing_physical_constants =
    2.0 * llnl::units::constants::mn / llnl::units::constants::h /
    (m_to_angstrom * tof_to_s);

constexpr auto tof_to_wavelength_physical_constants =
    tof_to_s * m_to_angstrom * llnl::units::constants::h /
    llnl::units::constants::mn;

template <class T> auto tof_to_dspacing(const T &d) {
  const auto &sourcePos = source_position(d.meta());
  const auto &samplePos = sample_position(d.meta());

  auto beam = samplePos - sourcePos;
  const auto l1 = norm(beam);
  beam /= l1;
  auto scattered = position(d.meta()) - samplePos;
  const auto l2 = norm(scattered);
  scattered /= l2;

  // l_total = l1 + l2
  auto conversionFactor(l1 + l2);

  conversionFactor *= Variable(tof_to_dspacing_physical_constants * sqrt(0.5));
  conversionFactor *= sqrt(1.0 * units::one - dot(beam, scattered));

  reciprocal(conversionFactor, conversionFactor);
  return conversionFactor;
}

template <class T>
static auto tof_to_wavelength(const T &d, const ConvertMode scatter) {
  return Variable(tof_to_wavelength_physical_constants) /
         flight_path_length(d.meta(), scatter);
}

template <class T> auto tof_to_energy(const T &d, const ConvertMode scatter) {
  if (incident_energy(d.meta()) || final_energy(d.meta()))
    throw std::runtime_error(
        "Data contains coords for incident or final energy. Conversion to "
        "energy for inelastic data not implemented yet.");
  // l_total = l1 + l2
  auto conversionFactor = flight_path_length(d.meta(), scatter);
  // l_total^2
  conversionFactor *= conversionFactor;
  conversionFactor *= Variable(tof_to_energy_physical_constants);
  return conversionFactor;
}

template <class T> auto tof_to_energy_transfer(const T &d) {
  const auto Ei = incident_energy(d.meta());
  const auto Ef = final_energy(d.meta());
  if (Ei && Ef)
    throw std::runtime_error(
        "Data contains coords for incident *and* final energy, cannot have "
        "both for inelastic scattering.");
  if (!Ei && !Ef)
    throw std::runtime_error(
        "Data contains neither coords for incident nor for final energy, this "
        "does not appear to be inelastic-scattering data, cannot convert to "
        "energy transfer.");
  auto l1_square = l1(d.meta());
  l1_square *= l1_square;
  l1_square *= Variable(tof_to_energy_physical_constants);
  auto l2_square = l2(d.meta());
  l2_square *= l2_square;
  l2_square *= Variable(tof_to_energy_physical_constants);
  if (Ei) { // Direct-inelastic.
    return std::tuple{-l2_square, sqrt(l1_square / Ei), -Ei};
  } else { // Indirect-inelastic.
    return std::tuple{std::move(l1_square), sqrt(l2_square / Ef), Variable(Ef)};
  }
}

template <class T> auto wavelength_to_q(const T &d) {
  return sin(scattering_angle(d.meta())) *
         (4.0 * scipp::pi<double> * units::one);
}

} // namespace scipp::neutron::constants
