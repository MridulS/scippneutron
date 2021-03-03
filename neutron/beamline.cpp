// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
/// @file
/// @author Simon Heybrock

#include <scipp/dataset/dataset.h>
#include <scipp/variable/operations.h>
#include <scipp/variable/transform.h>

#include "scipp/neutron/beamline.h"

using namespace scipp;

namespace scipp::neutron {

VariableConstView position(const dataset::CoordsConstView &meta) {
  return meta[Dim::Position];
}

VariableConstView source_position(const dataset::CoordsConstView &meta) {
  return meta[Dim("source_position")];
}

VariableConstView sample_position(const dataset::CoordsConstView &meta) {
  return meta[Dim("sample_position")];
}

Variable flight_path_length(const dataset::CoordsConstView &meta,
                            const ConvertMode scatter) {
  // TODO Avoid copies here and below if scipp buffer ownership model is changed
  if (meta.contains(Dim("L")))
    return copy(meta[Dim("L")]);
  // If there is not scattering this returns the straight distance from the
  // source, as required, e.g., for monitors or imaging.
  if (scatter == ConvertMode::Scatter)
    return l1(meta) + l2(meta);
  else
    return norm(position(meta) - source_position(meta));
}

Variable l1(const dataset::CoordsConstView &meta) {
  if (meta.contains(Dim("L1")))
    return copy(meta[Dim("L1")]);
  return norm(sample_position(meta) - source_position(meta));
}

Variable l2(const dataset::CoordsConstView &meta) {
  if (meta.contains(Dim("L2")))
    return copy(meta[Dim("L2")]);
  // Use transform to avoid temporaries. For certain unit conversions this can
  // cause a speedup >50%. Short version would be:
  //   return norm(position(meta) - sample_position(meta));
  return variable::transform<core::pair_self_t<Eigen::Vector3d>>(
      position(meta), sample_position(meta),
      overloaded{
          [](const auto &x, const auto &y) { return (x - y).norm(); },
          [](const units::Unit &x, const units::Unit &y) { return x - y; }});
}

Variable scattering_angle(const dataset::CoordsConstView &meta) {
  return 0.5 * units::one * two_theta(meta);
}

Variable cos_two_theta(const dataset::CoordsConstView &meta) {
  if (meta.contains(Dim("two_theta")))
    return cos(meta[Dim("two_theta")]);
  auto beam = sample_position(meta) - source_position(meta);
  const auto l1 = norm(beam);
  beam /= l1;
  auto scattered = position(meta) - sample_position(meta);
  const auto l2 = norm(scattered);
  scattered /= l2;
  return dot(beam, scattered);
}

Variable two_theta(const dataset::CoordsConstView &meta) {
  if (meta.contains(Dim("two_theta")))
    return copy(meta[Dim("two_theta")]);
  return acos(cos_two_theta(meta));
}

VariableConstView incident_energy(const dataset::CoordsConstView &meta) {
  return meta.contains(Dim::IncidentEnergy) ? meta[Dim::IncidentEnergy]
                                            : VariableConstView{};
}

VariableConstView final_energy(const dataset::CoordsConstView &meta) {
  return meta.contains(Dim::FinalEnergy) ? meta[Dim::FinalEnergy]
                                         : VariableConstView{};
}

} // namespace scipp::neutron
