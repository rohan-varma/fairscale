# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the BSD license found in the
# LICENSE file in the root directory of this source tree.

"""
Testing SSD Offload Module
"""

import filecmp
import os
import tempfile

import numpy as np
import torch

import fairscale.experimental.nn.ssd_offload as so


def _init():
    torch.manual_seed(0)
    np.random.seed(0)


def test_write_read():
    _init()

    with tempfile.NamedTemporaryFile() as f:
        ref_tensor = torch.rand((128), dtype=torch.float32)
        test_tensor = torch.zeros_like(ref_tensor)
        assert not torch.equal(ref_tensor, test_tensor)
        so.write(ref_tensor, f.name)
        so.read(test_tensor, f.name)
        assert torch.equal(ref_tensor, test_tensor)


def test_ssd_buffer_basic():
    _init()
    with tempfile.NamedTemporaryFile() as f:
        refa_tensor = torch.rand((128), dtype=torch.float32)
        refb_tensor = torch.rand((128), dtype=torch.float32)
        refc_tensor = torch.rand((128), dtype=torch.float32)
        buffer = torch.empty((1024), dtype=torch.float32)
        ssd_buf = so.SsdBuffer(buffer, f.name)

        hdl_a = ssd_buf.insert(refa_tensor)
        hdl_b = ssd_buf.insert(refb_tensor)
        hdl_c = ssd_buf.insert(refc_tensor)

        assert hdl_a.is_available()
        assert hdl_b.is_available()
        assert hdl_c.is_available()

        assert torch.equal(refa_tensor, hdl_a.get_tensor())
        assert torch.equal(refb_tensor, hdl_b.get_tensor())
        assert torch.equal(refc_tensor, hdl_c.get_tensor())

        tensors = ssd_buf.get_tensors()

        assert hdl_a in tensors
        assert hdl_b in tensors
        assert hdl_c in tensors

        # remove references so memory will be cleaned up
        buffer = None

        ssd_buf.to_disk()

        assert hdl_a.filename == f.name
        assert hdl_b.filename == f.name
        assert hdl_c.filename == f.name

        assert hdl_a.offset == 0
        assert hdl_b.offset == 128
        assert hdl_c.offset == 256

        assert not hdl_a.is_available()
        assert not hdl_b.is_available()
        assert not hdl_c.is_available()

        buffer = torch.empty((384), dtype=torch.float32)
        ssd_buf.from_disk(buffer)

        assert hdl_a.is_available()
        assert hdl_b.is_available()
        assert hdl_c.is_available()

        assert torch.equal(refa_tensor, hdl_a.get_tensor())
        assert torch.equal(refb_tensor, hdl_b.get_tensor())
        assert torch.equal(refc_tensor, hdl_c.get_tensor())


def test_torch_save_load():
    _init()
    orig_file = tempfile.NamedTemporaryFile()
    checkpoint_file = tempfile.NamedTemporaryFile()

    # TENSOR_SHAPE = (1024, 1024, 1024)
    # use smaller shape for unit tests
    TENSOR_SHAPE = (1024, 1024)
    ref_tensor = torch.rand(TENSOR_SHAPE, dtype=torch.float32)
    ref_ssd_tensor = so.SsdTensor.fromtensor(ref_tensor, orig_file.name)
    del ref_tensor
    # after deleting ref_tensor, memory usage should be very low
    # For save it shouldn't be more than 10x so.DEFAULT_CHUNK_SIZE
    so.torch_saver.save(ref_ssd_tensor, checkpoint_file.name)
    # below line saves file to orig_file.name+"_2"
    # Memory usage here should be O(1000 * so.DEFAULT_CHUNK_SIZE)
    # 1000x because that's how many elements the python unpickler
    # will buffer before passing to the SsdTensor
    test_ssd_tensor = torch.load(checkpoint_file)
    assert filecmp.cmp(orig_file.name, orig_file.name + "_2", shallow=False)
    os.unlink(orig_file.name + "_2")
