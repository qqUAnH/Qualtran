#  Copyright 2023 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import math
from typing import Dict, TYPE_CHECKING

import attrs
import cirq
import numpy as np
import pytest

from qualtran import GateWithRegisters, Signature
from qualtran.bloqs.arithmetic.multiplication import PlusEqualProduct
from qualtran.bloqs.qft.approximate_qft import (
    _approximate_qft_from_epsilon,
    _approximate_qft_small,
    ApproximateQFT,
)
from qualtran.bloqs.rotations.phase_gradient import PhaseGradientState
from qualtran.cirq_interop.testing import assert_decompose_is_consistent_with_t_complexity
from qualtran.testing import assert_valid_bloq_decomposition

if TYPE_CHECKING:
    from qualtran import BloqBuilder, SoquetT


@attrs.frozen
class TestApproximateQFT(GateWithRegisters):
    bitsize: int
    phase_bitsize: int
    with_reverse: bool

    @property
    def signature(self) -> 'Signature':
        return Signature.build(q=self.bitsize)

    def build_composite_bloq(self, bb: 'BloqBuilder', *, q: 'SoquetT') -> Dict[str, 'SoquetT']:
        phase_grad = bb.add(PhaseGradientState(self.phase_bitsize, exponent=-1))

        q, phase_grad = bb.add(
            ApproximateQFT(self.bitsize, self.phase_bitsize, self.with_reverse),
            q=q,
            phase_grad=phase_grad,
        )
        bb.add(PhaseGradientState(self.phase_bitsize).adjoint(), phase_grad=phase_grad)
        return {'q': q}


def test_approximate_qft_small_auto(bloq_autotester):
    bloq_autotester(_approximate_qft_small)


def test_approximate_qft_from_epsilon_auto(bloq_autotester):
    bloq_autotester(_approximate_qft_from_epsilon)


@pytest.mark.parametrize('n', [2, 3, 4, 5])
@pytest.mark.parametrize('without_reverse', [True, False])
def test_approximate_qft_exact(n: int, without_reverse: bool):
    qft_bloq = TestApproximateQFT(n, n, not without_reverse)
    qft_cirq = cirq.QuantumFourierTransformGate(n, without_reverse=without_reverse)
    np.testing.assert_allclose(cirq.unitary(qft_bloq), cirq.unitary(qft_cirq))
    np.testing.assert_allclose(cirq.unitary(qft_bloq**-1), cirq.unitary(qft_cirq**-1))

    assert_valid_bloq_decomposition(qft_bloq)


@pytest.mark.slow
def test_approximate_qft():
    num_qubits = 7
    phase_bitsize = 6
    qft_bloq = TestApproximateQFT(num_qubits, phase_bitsize, True)
    qft_cirq = cirq.QuantumFourierTransformGate(num_qubits, without_reverse=False)
    np.testing.assert_allclose(cirq.unitary(qft_bloq), cirq.unitary(qft_cirq), rtol=1e-2, atol=1e-2)

    assert_valid_bloq_decomposition(qft_bloq)


@pytest.mark.parametrize('n', [1000, 2000, 10000])
@pytest.mark.parametrize('bits_of_precision', [4, 7, 10])
def test_approximate_qft_with_eps(n: int, bits_of_precision: int):
    epsilon = 2 ** (-1 * bits_of_precision)
    phase_bitsize_for_single_bit_precision = ApproximateQFT.from_epsilon(n, 2**-1).phase_bitsize

    # factor of 2 takes care of the roughness of the upper-bound
    assert phase_bitsize_for_single_bit_precision < 2 * math.log2(n)
    approximate_qft = ApproximateQFT.from_epsilon(n, epsilon)

    # for each extra bit of precision, we only need 1 more bit in the phase register
    assert (
        approximate_qft.phase_bitsize
        == phase_bitsize_for_single_bit_precision + bits_of_precision - 1
    )


@pytest.mark.parametrize('n', [10, 123])
@pytest.mark.parametrize('with_reverse', [True, False])
def test_approximate_qft_t_complexity(n: int, with_reverse: bool):
    qft_bloq = ApproximateQFT(n, with_reverse=with_reverse)

    def f(n, b):
        t_complexity = 0
        for i in range(1, n):
            t_complexity += PlusEqualProduct(min(i, b - 1), 1, min(i, b - 1) + 1).t_complexity().t
        return t_complexity

    qft_t_complexity = qft_bloq.t_complexity()
    assert_decompose_is_consistent_with_t_complexity(qft_bloq)
    b = math.ceil(math.log2(n))
    assert qft_t_complexity.t == f(n, b) <= 8 * n * (math.log2(n) ** 2)
    assert qft_t_complexity.rotations == 0