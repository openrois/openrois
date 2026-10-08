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
    expect(openrois.CompletedParamsSchema).toBeDefined();
    expect(openrois.NotifyErrorParamsSchema).toBeDefined();
    expect(openrois.NotifyEventParamsSchema).toBeDefined();
    expect(openrois.ProfileChangedParamsSchema).toBeDefined();
  });

  it("exports Profile types", () => {
    expect(openrois.HRIComponentProfileSchema).toBeDefined();
    expect(openrois.ComponentFunctionSchema).toBeDefined();
    expect(openrois.HRIEngineProfileTypeSchema).toBeDefined();
    expect(openrois.ParameterProfileSchema).toBeDefined();
    expect(openrois.RoISIdentifierTypeSchema).toBeDefined();
  });

  it("exports the method catalog", () => {
    expect(openrois.RoISMethods).toBeDefined();
    expect(openrois.RoISMethodSchemas).toBeDefined();
    expect(openrois.RoISNotifications).toBeDefined();
    expect(openrois.RoISNotificationSchemas).toBeDefined();
    expect(openrois.RoISCommandTypes).toBeDefined();
    expect(openrois.JsonRpcErrorCode).toBeDefined();
    expect(openrois.ExecuteParamsSchema).toBeDefined();
    expect(openrois.GetProfileResultSchema).toBeDefined();
  });

  it("exports the condition parser and builders", () => {
    expect(openrois.parseCondition).toBeDefined();
    expect(openrois.ConditionError).toBeDefined();
    expect(openrois.componentRef("r/head")).toBe("component_ref = 'r/head'");
  });

  it("does NOT export Component types from root (use @openrois/interfaces/components)", () => {
    expect(openrois.PersonDetectedEventSchema).toBeUndefined();
  });

  it("exports the profile constants via components subpath", () => {
    expect(components.ROIS_COMMON_PROFILE).toBeDefined();
    expect(components.NAVIGATION_PROFILE).toBeDefined();
    expect(components.PERSON_DETECTION_PROFILE).toBeDefined();
    expect(components.REACTION_PROFILE).toBeDefined();
    expect(components.SPEECH_SYNTHESIS_PROFILE).toBeDefined();
    expect(components.SYSTEM_INFORMATION_PROFILE).toBeDefined();
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