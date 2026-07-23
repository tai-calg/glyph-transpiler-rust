from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CapabilityModel
from .contracts import ContractModel
from .contract_semantics import ContractSemanticModel
from .host_requirement_builder import build_host_requirements
from .host_requirements import HostRequirementModel
from .resource_flow import ResourceFlowModel, build_resource_flow
from .verification import VerificationReport, build_verification_report


@dataclass(frozen=True)
class Glyph04FeatureSet:
    capabilities: bool
    contracts: bool
    runtime_contracts: bool

    @property
    def enabled(self) -> bool:
        return self.capabilities or self.contracts or self.runtime_contracts


@dataclass(frozen=True)
class Glyph04DerivedModels:
    features: Glyph04FeatureSet
    resource_flow: ResourceFlowModel
    verification: VerificationReport
    host_requirements: HostRequirementModel


def detect_glyph04_features(
    capabilities: CapabilityModel,
    contracts: ContractModel,
    runtime_contracts: ContractSemanticModel,
) -> Glyph04FeatureSet:
    """Classify opt-in Glyph 0.4 axes without coupling them to output formats."""

    return Glyph04FeatureSet(
        capabilities=bool(
            capabilities.resources
            or capabilities.functions
            or capabilities.aggregates
            or capabilities.operations
        ),
        contracts=bool(contracts.declarations or contracts.applications),
        runtime_contracts=bool(
            runtime_contracts.worlds
            or runtime_contracts.protocols
            or runtime_contracts.handlers
            or runtime_contracts.laws
            or runtime_contracts.applications
        ),
    )


def derive_glyph04_models(
    capabilities: CapabilityModel,
    contracts: ContractModel,
    runtime_contracts: ContractSemanticModel,
) -> Glyph04DerivedModels:
    """Build each derived Glyph 0.4 model exactly once per compilation."""

    features = detect_glyph04_features(capabilities, contracts, runtime_contracts)
    if not features.enabled:
        return Glyph04DerivedModels(
            features,
            ResourceFlowModel.empty(),
            VerificationReport.empty(),
            HostRequirementModel.empty(),
        )

    resource_flow = build_resource_flow(capabilities)
    return Glyph04DerivedModels(
        features,
        resource_flow,
        build_verification_report(capabilities, runtime_contracts),
        build_host_requirements(capabilities, runtime_contracts, resource_flow),
    )
