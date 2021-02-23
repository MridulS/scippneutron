// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
/// @file
/// @author Simon Heybrock
#include <set>
#include <tuple>

#include <scipp/core/element/arg_list.h>

#include <scipp/variable/bucket_model.h>
#include <scipp/variable/transform.h>
#include <scipp/variable/util.h>

#include <scipp/dataset/bins.h>
#include <scipp/dataset/dataset.h>
#include <scipp/dataset/dataset_util.h>

#include "scipp/neutron/constants.h"
#include "scipp/neutron/conversions.h"
#include "scipp/neutron/convert.h"

using namespace scipp::variable;
using namespace scipp::dataset;

namespace scipp::neutron {

template <class T, class Op, class... Args>
T convert_generic(T &&d, const Dim from, const Dim to, Op op,
                  const Args &... args) {
  using core::element::arg_list;
  const auto op_ = overloaded{
      arg_list<double,
               std::tuple<float, std::conditional_t<true, double, Args>...>>,
      op};
  const auto items = iter(d);
  // 1. Transform coordinate
  if (d.coords().contains(from)) {
    const auto coord = d.coords()[from];
    if (!coord.dims().contains(merge(args.dims()...)))
      d.coords().set(from,
                     broadcast(coord, merge(args.dims()..., coord.dims())));
    transform_in_place(d.coords()[from], args..., op_);
  }
  // 2. Transform coordinates in bucket variables
  for (const auto &item : iter(d)) {
    if (item.dtype() != dtype<bucket<DataArray>>)
      continue;
    const auto &[indices, dim, buffer] =
        item.data().template constituents<bucket<DataArray>>();
    if (!buffer.coords().contains(from))
      continue;
    auto buffer_coord = buffer.coords().extract(from);
    auto coord = make_non_owning_bins(indices, dim, VariableView(buffer_coord));
    transform_in_place(coord, args..., op_);
    buffer.coords().set(to, std::move(buffer_coord));
  }

  // 3. Rename dims
  d.rename(from, to);
  return std::move(d);
}

namespace {
template <class T, class Op, class Tuple, std::size_t... I>
T convert_arg_tuple_impl(T &&d, const Dim from, const Dim to, Op op, Tuple &&t,
                         std::index_sequence<I...>) {
  return convert_generic(std::forward<T>(d), from, to, op,
                         std::get<I>(std::forward<Tuple>(t))...);
}
} // namespace

template <class T, class Op, class Tuple>
T convert_arg_tuple(T &&d, const Dim from, const Dim to, Op op, Tuple &&t) {
  return convert_arg_tuple_impl(
      std::forward<T>(d), from, to, op, std::forward<Tuple>(t),
      std::make_index_sequence<
          std::tuple_size_v<std::remove_reference_t<Tuple>>>{});
}

template <class T>
static T convert_with_factor(T &&d, const Dim from, const Dim to,
                             const Variable &factor) {
  return convert_generic(
      std::forward<T>(d), from, to,
      [](auto &coord, const auto &c) { coord *= c; }, factor);
}

namespace {

template <class T> T coords_to_attrs(T &&x, const Dim from, const Dim to) {
  const auto to_attr = [&](const Dim field) {
    if (!x.coords().contains(field))
      return;
    Variable coord(x.coords()[field]);
    if constexpr (std::is_same_v<std::decay_t<T>, Dataset>) {
      x.coords().erase(field);
      for (const auto &item : iter(x))
        item.attrs().set(field, coord);
    } else {
      x.coords().erase(field);
      x.attrs().set(field, coord);
    }
  };
  // Will be replaced by explicit flag
  bool scatter = x.coords().contains(Dim("sample-position"));
  if (scatter) {
    std::set<Dim> pos_invariant{Dim::DSpacing, Dim::Q};
    if (pos_invariant.count(to))
      to_attr(Dim::Position);
  } else if (from == Dim::Tof) {
    to_attr(Dim::Position);
  }
  return std::move(x);
}

template <class T> T attrs_to_coords(T &&x, const Dim from, const Dim to) {
  const auto to_coord = [&](const Dim field) {
    auto &&range = iter(x);
    if (!range.begin()->attrs().contains(field))
      return;
    Variable attr(range.begin()->attrs()[field]);
    if constexpr (std::is_same_v<std::decay_t<T>, Dataset>) {
      for (const auto &item : range) {
        core::expect::equals(item.attrs()[field], attr);
        item.attrs().erase(field);
      }
      x.coords().set(field, attr);
    } else {
      x.attrs().erase(field);
      x.coords().set(field, attr);
    }
  };
  // Will be replaced by explicit flag
  bool scatter = x.coords().contains(Dim("sample-position"));
  if (scatter) {
    std::set<Dim> pos_invariant{Dim::DSpacing, Dim::Q};
    if (pos_invariant.count(from))
      to_coord(Dim::Position);
  } else if (to == Dim::Tof) {
    to_coord(Dim::Position);
  }
  return std::move(x);
}

} // namespace

template <class T> T convert_impl(T d, const Dim from, const Dim to) {
  for (const auto &item : iter(d))
    core::expect::notCountDensity(item.unit());
  d = attrs_to_coords(std::move(d), from, to);
  // This will need to be cleanup up in the future, but it is unclear how to do
  // so in a future-proof way. Some sort of double-dynamic dispatch based on
  // `from` and `to` will likely be required (with conversions helpers created
  // by a dynamic factory based on `Dim`). Conceptually we are dealing with a
  // bidirectional graph, and we would like to be able to find the shortest
  // paths between any two points, without defining all-to-all connections.
  // Approaches based on, e.g., a map of conversions and constants is also
  // tricky, since in particular the conversions are generic lambdas (passable
  // to `transform`) and are not readily stored as function pointers or
  // std::function.
  if ((from == Dim::Tof) && (to == Dim::DSpacing))
    return convert_with_factor(std::move(d), from, to,
                               constants::tof_to_dspacing(d));
  if ((from == Dim::DSpacing) && (to == Dim::Tof))
    return convert_with_factor(std::move(d), from, to,
                               reciprocal(constants::tof_to_dspacing(d)));

  if ((from == Dim::Tof) && (to == Dim::Wavelength))
    return convert_with_factor(std::move(d), from, to,
                               constants::tof_to_wavelength(d));
  if ((from == Dim::Wavelength) && (to == Dim::Tof))
    return convert_with_factor(std::move(d), from, to,
                               reciprocal(constants::tof_to_wavelength(d)));

  if ((from == Dim::Tof) && (to == Dim::Energy))
    return convert_generic(std::move(d), from, to, conversions::tof_to_energy,
                           constants::tof_to_energy(d));
  if ((from == Dim::Energy) && (to == Dim::Tof))
    return convert_generic(std::move(d), from, to, conversions::energy_to_tof,
                           constants::tof_to_energy(d));

  if ((from == Dim::Tof) && (to == Dim::EnergyTransfer))
    return convert_arg_tuple(std::move(d), from, to,
                             conversions::tof_to_energy_transfer,
                             constants::tof_to_energy_transfer(d));
  if ((from == Dim::EnergyTransfer) && (to == Dim::Tof))
    return convert_arg_tuple(std::move(d), from, to,
                             conversions::energy_transfer_to_tof,
                             constants::tof_to_energy_transfer(d));

  // lambda <-> Q conversion is symmetric
  if (((from == Dim::Wavelength) && (to == Dim::Q)) ||
      ((from == Dim::Q) && (to == Dim::Wavelength)))
    return convert_generic(std::move(d), from, to, conversions::wavelength_to_q,
                           constants::wavelength_to_q(d));

  try {
    // Could get better performance by doing a direct conversion.
    return convert_impl(convert_impl(std::move(d), from, Dim::Tof), Dim::Tof,
                        to);
  } catch (const except::UnitError &) {
    throw except::UnitError("Conversion between " + to_string(from) + " and " +
                            to_string(to) +
                            " not implemented yet or not possible.");
  }
}

DataArray convert(DataArray d, const Dim from, const Dim to) {
  return coords_to_attrs(convert_impl(std::move(d), from, to), from, to);
}

DataArray convert(const DataArrayConstView &d, const Dim from, const Dim to) {
  return convert(DataArray(d), from, to);
}

Dataset convert(Dataset d, const Dim from, const Dim to) {
  return coords_to_attrs(convert_impl(std::move(d), from, to), from, to);
}

Dataset convert(const DatasetConstView &d, const Dim from, const Dim to) {
  return convert(Dataset(d), from, to);
}

} // namespace scipp::neutron
