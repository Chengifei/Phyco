/* Copyright 2017-2018 by Yifei Zheng
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * This is the meta-header for any ATOM project.
 */

#ifndef ATOM_INCLUDES_HPP
#define ATOM_INCLUDES_HPP
#include "env.hpp"
#include "combination.hpp"
#include <memory>
#include <vector>
#include <fstream>
#include <iterator>
#include "math/solvers.hpp"
#include "math/calculus.hpp"
#include "math/operators.hpp"

namespace types {

template <typename T>
using log = std::vector<T>;

}
#endif
