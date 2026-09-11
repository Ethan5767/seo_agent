"use client";

import React, { useState, useMemo } from "react";
import { ALL_PLATFORM_TOOLS, type CatalogToolItem } from "@/app/toolsCatalogData";
import type { ReaiTab } from "./types";

interface ToolDirectoryProps {
  onLaunchTool?: (tool: CatalogToolItem) => void;
  onNavigateTab?: (tab: ReaiTab) => void;
}

export function ToolDirectory({ onLaunchTool, onNavigateTab }: ToolDirectoryProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("All");

  const categories = useMemo(() => {
    const cats = new Set(ALL_PLATFORM_TOOLS.map((t) => t.category));
    return ["All", ...Array.from(cats)];
  }, []);

  const filteredTools = useMemo(() => {
    return ALL_PLATFORM_TOOLS.filter((t) => {
      const matchesCat = selectedCategory === "All" || t.category === selectedCategory;
      const matchesSearch =
        searchTerm === "" ||
        t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.desc.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.engine.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesCat && matchesSearch;
    });
  }, [searchTerm, selectedCategory]);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: 0 }}>
              All Tools Directory
            </h1>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "4px 0 0" }}>
              Comprehensive catalog of all 160 specialized SEO, AEO, and technical audit engines.
            </p>
          </div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              padding: "4px 10px",
              borderRadius: 6,
              background: "#eff6ff",
              color: "#1d4ed8",
              border: "1px solid #bfdbfe",
            }}
          >
            {filteredTools.length} of {ALL_PLATFORM_TOOLS.length} Tools
          </div>
        </div>

        {/* Search & Category Filter Bar */}
        <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
          <input
            type="search"
            aria-label="Search tools by name, description, or engine"
            placeholder="Search all 160 tools by keyword..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              flex: 1,
              minWidth: 240,
              padding: "8px 12px",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 13,
            }}
          />

          <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 2 }}>
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedCategory(cat)}
                style={{
                  background: selectedCategory === cat ? "#0f172a" : "#ffffff",
                  color: selectedCategory === cat ? "#ffffff" : "#475569",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: selectedCategory === cat ? 700 : 500,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tools Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
        {filteredTools.map((tool) => (
          <div
            key={tool.id}
            style={{
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: "14px 16px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: "#f1f5f9",
                    color: "#475569",
                  }}
                >
                  {tool.category}
                </span>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: "#e0f2fe",
                    color: "#0369a1",
                  }}
                >
                  {tool.engine}
                </span>
              </div>

              <h4 style={{ fontSize: 13.5, fontWeight: 700, color: "#1e293b", margin: "0 0 6px" }}>
                {tool.name}
              </h4>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0, lineHeight: 1.4 }}>
                {tool.desc}
              </p>
            </div>

            <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
              <button
                type="button"
                onClick={() => {
                  if (onLaunchTool) {
                    onLaunchTool(tool);
                  } else if (onNavigateTab && tool.targetTab) {
                    onNavigateTab(tool.targetTab as ReaiTab);
                  }
                }}
                style={{
                  width: "100%",
                  padding: "6px 10px",
                  background: "#f8fafc",
                  color: "#2563eb",
                  border: "1px solid #bfdbfe",
                  borderRadius: 4,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Open {tool.targetTab || "Tool"} →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
