#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

#!/usr/bin/env python3

from dataclasses import dataclass
from typing import Dict, Optional, Type, Union

import torch

from torchrec.distributed.embedding import (
    EmbeddingCollectionContext,
    EmbeddingCollectionSharder,
    ShardedEmbeddingCollection,
)

from torchrec.distributed.embedding_types import KJTList
from torchrec.distributed.mc_embedding_modules import (
    BaseManagedCollisionEmbeddingCollectionSharder,
    BaseShardedManagedCollisionEmbeddingCollection,
)
from torchrec.distributed.mc_modules import ManagedCollisionCollectionSharder
from torchrec.distributed.types import (
    ParameterSharding,
    QuantizedCommCodecs,
    ShardingEnv,
)
from torchrec.modules.mc_embedding_modules import ManagedCollisionEmbeddingCollection


@dataclass
class ManagedCollisionEmbeddingCollectionContext(EmbeddingCollectionContext):
    evictions_per_table: Optional[Dict[str, Optional[torch.Tensor]]] = None
    remapped_kjt: Optional[KJTList] = None

    def record_stream(self, stream: torch.cuda.streams.Stream) -> None:
        super().record_stream(stream)
        if self.evictions_per_table:
            #  pyre-ignore
            for value in self.evictions_per_table.values():
                if value is None:
                    continue
                value.record_stream(stream)
        if self.remapped_kjt is not None:
            self.remapped_kjt.record_stream(stream)


class ShardedManagedCollisionEmbeddingCollection(
    BaseShardedManagedCollisionEmbeddingCollection[
        ManagedCollisionEmbeddingCollectionContext
    ]
):
    def __init__(
        self,
        module: ManagedCollisionEmbeddingCollection,
        table_name_to_parameter_sharding: Dict[str, ParameterSharding],
        ec_sharder: EmbeddingCollectionSharder,
        mc_sharder: ManagedCollisionCollectionSharder,
        # TODO - maybe we need this to manage unsharded/sharded consistency/state consistency
        env: ShardingEnv,
        device: torch.device,
    ) -> None:
        super().__init__(
            module,
            table_name_to_parameter_sharding,
            ec_sharder,
            mc_sharder,
            env,
            device,
        )

        # For consistency with embeddingbag
        # pyre-ignore [8]
        self._embedding_collection: ShardedEmbeddingCollection = self._embedding_module

    def create_context(
        self,
    ) -> ManagedCollisionEmbeddingCollectionContext:
        return ManagedCollisionEmbeddingCollectionContext(sharding_contexts=[])


class ManagedCollisionEmbeddingCollectionSharder(
    BaseManagedCollisionEmbeddingCollectionSharder[ManagedCollisionEmbeddingCollection]
):
    def __init__(
        self,
        ec_sharder: Optional[EmbeddingCollectionSharder] = None,
        mc_sharder: Optional[ManagedCollisionCollectionSharder] = None,
        qcomm_codecs_registry: Optional[Dict[str, QuantizedCommCodecs]] = None,
    ) -> None:
        super().__init__(
            ec_sharder
            or EmbeddingCollectionSharder(qcomm_codecs_registry=qcomm_codecs_registry),
            mc_sharder or ManagedCollisionCollectionSharder(),
            qcomm_codecs_registry=qcomm_codecs_registry,
        )

    def shard(
        self,
        module: ManagedCollisionEmbeddingCollection,
        params: Dict[str, ParameterSharding],
        env: ShardingEnv,
        device: Optional[torch.device] = None,
    ) -> ShardedManagedCollisionEmbeddingCollection:

        if device is None:
            device = torch.device("cuda")

        return ShardedManagedCollisionEmbeddingCollection(
            module,
            params,
            # pyre-ignore [6]
            ec_sharder=self._e_sharder,
            mc_sharder=self._mc_sharder,
            env=env,
            device=device,
        )

    @property
    def module_type(self) -> Type[ManagedCollisionEmbeddingCollection]:
        return ManagedCollisionEmbeddingCollection
