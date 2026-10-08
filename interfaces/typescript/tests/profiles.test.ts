// The generator writes the constants from schema/profiles.json, and CI checks that
// src is up to date with it. These tests check what the constants hold.
import { describe, it, expect } from "vitest";
import { HRIComponentProfileSchema, componentTypeUrn } from "../src";
import type { HRIComponentProfile } from "../src";
import {
  NAVIGATION_PROFILE,
  PERSON_DETECTION_PROFILE,
  REACTION_PROFILE,
  ROIS_COMMON_PROFILE,
  SPEECH_SYNTHESIS_PROFILE,
  SYSTEM_INFORMATION_PROFILE,
} from "../src/components";

const ROIS_COMMON_URN = "urn:x-rois:def:Component:OMG::RoISCommon";

const constants: Record<string, HRIComponentProfile> = {
  ROIS_COMMON_PROFILE,
  NAVIGATION_PROFILE,
  PERSON_DETECTION_PROFILE,
  REACTION_PROFILE,
  SPEECH_SYNTHESIS_PROFILE,
  SYSTEM_INFORMATION_PROFILE,
};

const names = (messages: readonly { name: string }[] = []) => messages.map((m) => m.name);

describe("Profile constants", () => {
  it("parse as component profiles", () => {
    for (const profile of Object.values(constants)) {
      expect(HRIComponentProfileSchema.parse(profile)).toEqual(profile);
    }
  });

  it("list the RoIS_Common messages first where the type includes it", () => {
    for (const profile of [
      NAVIGATION_PROFILE,
      PERSON_DETECTION_PROFILE,
      REACTION_PROFILE,
      SPEECH_SYNTHESIS_PROFILE,
    ]) {
      expect(profile.sub_component_profiles).toEqual([ROIS_COMMON_URN]);
      expect(names(profile.command_profiles)).toEqual(["start", "stop", "suspend", "resume"]);
      expect(names(profile.query_profiles)[0]).toBe("component_status");
    }
    expect(SYSTEM_INFORMATION_PROFILE.sub_component_profiles).toEqual([]);
    expect(names(SYSTEM_INFORMATION_PROFILE.query_profiles)).toEqual(["robot_position", "engine_status"]);
  });

  it("carry the RoSO function of their type", () => {
    expect(NAVIGATION_PROFILE.function).toBe("actuation");
    expect(PERSON_DETECTION_PROFILE.function).toBe("sensing");
    expect(REACTION_PROFILE.function).toBe("actuation");
    expect(SPEECH_SYNTHESIS_PROFILE.function).toBe("actuation");
    expect(SYSTEM_INFORMATION_PROFILE.function).toBeNull();
  });

  it("name their type in the identifier", () => {
    expect(componentTypeUrn(NAVIGATION_PROFILE.identifier)).toBe("urn:x-rois:def:component:OMG::Navigation");
    expect(ROIS_COMMON_PROFILE.identifier.code).toBe("RoISCommon");
    expect(componentTypeUrn(SPEECH_SYNTHESIS_PROFILE.identifier)).toBe(
      "urn:x-rois:def:component:OMG::SpeechSynthesis",
    );
  });

  it("give SpeechSynthesis its queries and parameters with the XML defaults", () => {
    expect(names(SPEECH_SYNTHESIS_PROFILE.query_profiles)).toEqual([
      "component_status",
      "synthesizable_languages",
      "available_voices",
    ]);
    const defaults = Object.fromEntries(
      (SPEECH_SYNTHESIS_PROFILE.parameter_profiles ?? []).map((p) => [p.name, p.default_value]),
    );
    expect(defaults).toEqual({
      speech_text: "",
      ssml_text: "",
      volume: "50",
      language: "en",
      character: "default",
    });
  });
});
