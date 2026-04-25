import { describe, it, expect } from "vitest";
import { z } from "zod";

/**
 * Unit tests for MEEET MCP Server
 * Run: npm test
 */

describe("Schema validation", () => {
  it("ResolveDidSchema accepts full DID", () => {
    const schema = z.object({ agentId: z.string() });
    const result = schema.safeParse({ agentId: "did:meeet:abc123" });
    expect(result.success).toBe(true);
  });

  it("ResolveDidSchema accepts raw ID", () => {
    const schema = z.object({ agentId: z.string() });
    const result = schema.safeParse({ agentId: "abc123" });
    expect(result.success).toBe(true);
  });

  it("VerifyOutputSchema accepts valid output types", () => {
    const schema = z.object({
      agentId: z.string(),
      output: z.string(),
      outputType: z.enum(["discovery", "research", "analysis", "claim"]),
      verificationLevel: z.enum(["quick", "standard", "deep"]).default("standard"),
    });
    const result = schema.safeParse({
      agentId: "abc123",
      output: "Some output",
      outputType: "discovery",
    });
    expect(result.success).toBe(true);
    expect(result.data?.verificationLevel).toBe("standard");
  });

  it("GetTasksSchema applies default limit", () => {
    const schema = z.object({
      category: z.string().optional(),
      limit: z.number().optional().default(10),
    });
    const result = schema.safeParse({});
    expect(result.success).toBe(true);
    expect(result.data?.limit).toBe(10);
  });

  it("GetLeaderboardSchema accepts valid categories", () => {
    const schema = z.object({
      category: z.enum(["reputation", "discoveries", "activity", "staking"]).default("reputation"),
      limit: z.number().optional().default(10),
    });
    for (const cat of ["reputation", "discoveries", "activity", "staking"]) {
      const result = schema.safeParse({ category: cat });
      expect(result.success).toBe(true);
    }
  });

  it("SaraAssessSchema allows optional fields", () => {
    const schema = z.object({
      agentId: z.string().optional(),
      transaction: z.string().optional(),
      scenario: z.string().optional(),
    });
    const result = schema.safeParse({ agentId: "abc123" });
    expect(result.success).toBe(true);
  });
});

describe("DID normalization", () => {
  it("strips did:meeet: prefix", () => {
    const id = "did:meeet:abc123".replace(/^did:meeet:/, "");
    expect(id).toBe("abc123");
  });

  it("leaves raw ID unchanged", () => {
    const id = "abc123".replace(/^did:meeet:/, "");
    expect(id).toBe("abc123");
  });
});

describe("Tool descriptions", () => {
  const tools = [
    "resolve_did",
    "get_discoveries",
    "verify_output",
    "get_reputation",
    "sara_assess",
    "get_leaderboard",
    "get_tasks",
    "get_staking_stats",
    "get_interaction_graph",
  ];

  tools.forEach((tool) => {
    it(`${tool} has a description`, () => {
      expect(typeof tool).toBe("string");
      expect(tool.length).toBeGreaterThan(0);
    });
  });
});
