import { describe, it, expect } from "vitest";
import * as openrois from "../src";
import * as components from "../src/components";

describe("Export completeness", () => {
  it("exports core HRI types", () => {
    expect(openrois.ResultSchema).toBeDefined();
    expect(openrois.ParameterSchema).toBeDefined();
    expect(openrois.ArgumentSchema).toBeDefined();
    expect(openrois.CommandUnitSchema).toBeDefined();
    expect(openrois.CommandUnitSequenceSchema).toBeDefined();
    expect(openrois.ConcurrentCommandsSchema).toBeDefined();
    expect(openrois.ReturnCodeSchema).toBeDefined();
  });

  it("exports Common types", () => {
    expect(openrois.ComponentStatusSchema).toBeDefined();
    expect(openrois.StreamStatusSchema).toBeDefined();
  });

  it("exports Service types", () => {
    expect(openrois.CompletedStatusSchema).toBeDefined();
    expect(openrois.ErrorTypeSchema).toBeDefined();
    expect(openrois.CompletedEventSchema).toBeDefined();
    expect(openrois.NotifyErrorEventSchema).toBeDefined();
    expect(openrois.NotifyEventPayloadSchema).toBeDefined();
  });

  it("exports Bus types", () => {
    expect(openrois.ComponentContractError).toBeDefined();
    expect(openrois.BusAdapterError).toBe(openrois.ComponentContractError);
    expect(openrois.ComponentNotFoundError).toBeDefined();
    expect(openrois.DiscoverRequestSchema).toBeDefined();
    expect(openrois.DiscoverResponseSchema).toBeDefined();
    expect(openrois.CommandRequestSchema).toBeDefined();
    expect(openrois.InvokeResponseSchema).toBeDefined();
    expect(openrois.QueryRequestSchema).toBeDefined();
    expect(openrois.QueryResponseSchema).toBeDefined();
    expect(openrois.SubscribeRequestSchema).toBeDefined();
    expect(openrois.SubscribeResponseSchema).toBeDefined();
    expect(openrois.EventEnvelopeSchema).toBeDefined();
  });

  it("exports Profile types", () => {
    expect(openrois.HRIComponentProfileSchema).toBeDefined();
    expect(openrois.HRIEngineProfileTypeSchema).toBeDefined();
    expect(openrois.ParameterProfileSchema).toBeDefined();
    expect(openrois.RoISIdentifierTypeSchema).toBeDefined();
  });

  it("does NOT export Component types from root (use @openrois/interfaces/components)", () => {
    expect(openrois.PersonDetectedEventSchema).toBeUndefined();
  });

  it("exports Component types via components subpath", () => {
    expect(components.PersonDetectedEventSchema).toBeDefined();
    expect(components.PersonDetectionStatusResultSchema).toBeDefined();
    expect(components.NavigationSetParameterSchema).toBeDefined();
    expect(components.NavigationSetParameterResultSchema).toBeDefined();
    expect(components.NavigationGetParameterResultSchema).toBeDefined();
    expect(components.NavigationStatusResultSchema).toBeDefined();
    expect(components.NavigationReachedTargetEventSchema).toBeDefined();
    expect(components.SystemInformationRobotPositionResultSchema).toBeDefined();
    expect(components.SystemInformationEngineStatusResultSchema).toBeDefined();
  });
});