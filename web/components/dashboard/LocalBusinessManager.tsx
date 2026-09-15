"use client";

import React, { useState, useEffect } from "react";
import { GoogleServicesHub } from "./GoogleServicesHub";
import { authedFetch } from "@/lib/authedFetch";

interface BusinessHours {
  open: string;
  close: string;
  isClosed: boolean;
}

interface SpecialHour {
  id: string;
  date: string;
  occasion: string;
  isClosed: boolean;
  openTime?: string;
  closeTime?: string;
}

/** As `/api/local-seo/reviews` sends it. The UI read authorName/rating/replyText, none of which exist. */
interface Review {
  id: string;
  reviewer: string | null;
  /** Google's enum ("ONE".."FIVE"). */
  starRating: string | null;
  createTime: string | null;
  comment: string | null;
  reply: string | null;
  replyTime: string | null;
}

/** As `/api/local-seo/posts` sends it. Google's list call returns no view or click counts. */
interface GooglePost {
  name: string | null;
  topicType: string | null;
  summary: string | null;
  createTime: string | null;
  state: string | null;
  searchUrl: string | null;
}

const STAR_WORDS: Record<string, number> = { ONE: 1, TWO: 2, THREE: 3, FOUR: 4, FIVE: 5 };
/** 1-5 from Google's enum, or null when Google gave none. */
export function starsOf(rating: string | number | null | undefined): number | null {
  if (typeof rating === "number") return rating >= 1 && rating <= 5 ? rating : null;
  return rating ? STAR_WORDS[rating] ?? null : null;
}

const DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const hhmm = (t: any) => `${String(t?.hours ?? 0).padStart(2, "0")}:${String(t?.minutes ?? 0).padStart(2, "0")}`;

/**
 * Google's `regularHours.periods` as one entry per day it lists. A day Google
 * does not list is absent (shown as "not listed on Google"), never a default.
 */
export function hoursFromGoogle(periods: any): Record<string, BusinessHours> {
  const out: Record<string, BusinessHours> = {};
  if (!Array.isArray(periods)) return out;
  for (const p of periods) {
    const day = String(p?.openDay || "").toLowerCase();
    if (!DAY_KEYS.includes(day)) continue;
    out[day] = { open: hhmm(p.openTime), close: hhmm(p.closeTime), isClosed: false };
  }
  return out;
}

type SubTab = "info" | "hours" | "reviews" | "review_boost" | "posts" | "local_grid" | "nap_audit" | "insights";

export interface LocalBusinessManagerProps {
  /**
   * Drive the sub-section from outside, so the sidebar can list these eight
   * the way the AI section lists its five. Left undefined, the component keeps
   * its own state and the in-page tab bar behaves as before.
   */
  subTab?: SubTab;
  onSubTabChange?: (tab: SubTab) => void;
}

export function LocalBusinessManager({
  subTab: controlledSubTab,
  onSubTabChange,
}: LocalBusinessManagerProps = {}) {
  const [uncontrolledSubTab, setUncontrolledSubTab] = useState<SubTab>("info");
  const subTab = controlledSubTab ?? uncontrolledSubTab;
  const setSubTab = (tab: SubTab) => {
    setUncontrolledSubTab(tab);
    onSubTabChange?.(tab);
  };
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Business state
  const [connected, setConnected] = useState(false);
  const [accountType, setAccountType] = useState<string>("none");
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [dataStatus, setDataStatus] = useState<string>("Loading...");

  const [businessName, setBusinessName] = useState("");
  const [primaryCategory, setPrimaryCategory] = useState("");
  const [phone, setPhone] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [appointmentUrl, setAppointmentUrl] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("");
  const [serviceAreas, setServiceAreas] = useState<string[]>([]);
  const [serviceAreaInput, setServiceAreaInput] = useState("");

  // Empty until Google returns the listing's hours. These defaulted to
  // 08:00-18:00 weekdays, shown as the business's hours whether or not Google
  // had any.
  const [regularHours, setRegularHours] = useState<Record<string, BusinessHours>>({});

  const [specialHours, setSpecialHours] = useState<SpecialHour[]>([]);
  const [newHolidayDate, setNewHolidayDate] = useState("");
  const [newHolidayOccasion, setNewHolidayOccasion] = useState("");

  // Reviews state
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewFilter, setReviewFilter] = useState<"all" | "unreplied" | "5star" | "negative">("all");
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [generatingAi, setGeneratingAi] = useState<string | null>(null);
  const [submittingReply, setSubmittingReply] = useState<string | null>(null);

  // Posts state
  const [posts, setPosts] = useState<GooglePost[]>([]);
  const [newPostSummary, setNewPostSummary] = useState("");
  const [newPostType, setNewPostType] = useState<"STANDARD" | "OFFER" | "EVENT">("STANDARD");
  const [newPostAction, setNewPostAction] = useState<"LEARN_MORE" | "CALL" | "BOOK">("LEARN_MORE");
  const [newPostUrl, setNewPostUrl] = useState("");
  const [publishingPost, setPublishingPost] = useState(false);

  // Review Boost state
  // ChIJN1t_tDeuEmsRUsoyG83frY4 is Google's own documentation sample (a Sydney
  // address). It was rendered into the live review link the client prints on
  // counter signage, so every printed QR code pointed at Google's example
  // business.
  const [placeId, setPlaceId] = useState("");
  const [reviewCopied, setReviewCopied] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState<"sms" | "email" | "receipt">("sms");

  // Insights state
  const [insights, setInsights] = useState<any>(null);

  // Load initial data
  const fetchData = async () => {
    try {
      setLoading(true);
      const [bizRes, revRes, postRes, insRes] = await Promise.all([
        authedFetch("/api/local-seo/business").then((r) => r.json()),
        authedFetch("/api/local-seo/reviews").then((r) => r.json()),
        authedFetch("/api/local-seo/posts").then((r) => r.json()),
        authedFetch("/api/local-seo/insights").then((r) => r.json()),
      ]);

      // Connection state and the reason string are reported whether or not
      // Google returned a location, so an unavailable state says why instead of
      // sitting on "Loading...".
      setConnected(Boolean(bizRes.connected));
      setAccountType(bizRes.accountType || "none");
      setActiveAccount(bizRes.activeAccount ?? null);
      setDataStatus(bizRes.dataStatus || "No status reported.");

      if (bizRes.business) {
        setBusinessName(bizRes.business.businessName || "");
        setPrimaryCategory(bizRes.business.primaryCategory || "");
        setPhone(bizRes.business.phone || "");
        setWebsiteUrl(bizRes.business.websiteUrl || "");
        setAppointmentUrl(bizRes.business.appointmentUrl || "");
        setStreet(bizRes.business.address?.street || "");
        setCity(bizRes.business.address?.city || "");
        setStateCode(bizRes.business.address?.state || "");
        setPostalCode(bizRes.business.address?.postalCode || "");
        setCountry(bizRes.business.address?.country || "");
        setServiceAreas(bizRes.business.serviceAreas || []);
        setRegularHours(hoursFromGoogle(bizRes.business.regularHours));
        if (bizRes.business.specialHours) setSpecialHours(bizRes.business.specialHours);
      }

      if (revRes.reviews) setReviews(revRes.reviews);
      if (postRes.posts) setPosts(postRes.posts);
      // The whole response: the tab reads `insights.metrics` and `insights.dataStatus`.
      // Storing only `metrics` made that `insights.metrics.metrics`, so real
      // Business Profile numbers never showed.
      setInsights(insRes);
    } catch (err: any) {
      // No fixture to fall back to: state starts empty and stays empty.
      setDataStatus(`Could not reach the Business Profile API: ${err?.message || "network error"}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSaveBusiness = async () => {
    try {
      setSaving(true);
      setSaveSuccess(null);
      setActionError(null);
      const res = await authedFetch("/api/local-seo/business", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business: {
            businessName,
            primaryCategory,
            phone,
            websiteUrl,
            appointmentUrl,
            address: { street, city, state: stateCode, postalCode, country },
            serviceAreas,
          },
          regularHours,
          specialHours,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success) {
        setSaveSuccess("Changes saved to Google Business Profile.");
        setTimeout(() => setSaveSuccess(null), 4000);
      } else {
        setActionError(data?.error || `Saving failed: HTTP ${res.status}.`);
      }
    } catch (err: any) {
      setActionError(err?.message || "Saving failed.");
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAiReply = async (reviewId: string, tone: string = "professional") => {
    try {
      setGeneratingAi(reviewId);
      const res = await authedFetch("/api/local-seo/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "generate_ai_reply", reviewId, tone }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.generatedReply) {
        setReplyDrafts((prev) => ({ ...prev, [reviewId]: data.generatedReply }));
      } else {
        setActionError(data?.error || `Drafting a reply failed: HTTP ${res.status}.`);
      }
    } finally {
      setGeneratingAi(null);
    }
  };

  const handleSubmitReply = async (reviewId: string) => {
    const text = replyDrafts[reviewId];
    if (!text) return;
    try {
      setSubmittingReply(reviewId);
      const res = await authedFetch("/api/local-seo/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "submit_reply", reviewId, replyText: text }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) setActionError(data?.error || `Posting the reply failed: HTTP ${res.status}.`);
      if (res.ok && data.success && data.review) {
        setReviews((prev) => prev.map((r) => (r.id === reviewId ? data.review : r)));
        setReplyDrafts((prev) => {
          const next = { ...prev };
          delete next[reviewId];
          return next;
        });
      }
    } finally {
      setSubmittingReply(null);
    }
  };

  const handlePublishPost = async () => {
    if (!newPostSummary.trim()) return;
    try {
      setPublishingPost(true);
      const res = await authedFetch("/api/local-seo/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topicType: newPostType,
          summary: newPostSummary,
          callToAction: {
            actionType: newPostAction,
            url: newPostUrl,
          },
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success && data.post) {
        setPosts((prev) => [data.post, ...prev]);
        setNewPostSummary("");
        setSaveSuccess("Google Post published.");
        setTimeout(() => setSaveSuccess(null), 4000);
      } else {
        setActionError(data?.error || `Publishing failed: HTTP ${res.status}.`);
      }
    } finally {
      setPublishingPost(false);
    }
  };

  const handleAddHoliday = () => {
    if (!newHolidayDate || !newHolidayOccasion) return;
    const item: SpecialHour = {
      id: `sh-${Date.now()}`,
      date: newHolidayDate,
      occasion: newHolidayOccasion,
      isClosed: true,
    };
    setSpecialHours((prev) => [...prev, item]);
    setNewHolidayDate("");
    setNewHolidayOccasion("");
  };

  const handleRemoveHoliday = (id: string) => {
    setSpecialHours((prev) => prev.filter((h) => h.id !== id));
  };

  const daysOfWeek = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

  // Filter reviews
  const filteredReviews = reviews.filter((r) => {
    const stars = starsOf(r.starRating);
    if (reviewFilter === "unreplied") return !r.reply;
    if (reviewFilter === "5star") return stars === 5;
    if (reviewFilter === "negative") return stars !== null && stars <= 2;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Top Header Card */}
      <div
        style={{
          background: "#ffffff",
          borderRadius: 8,
          border: "1px solid #e2e8f0",
          padding: "16px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", margin: 0 }}>
              {businessName || "Local Business & Google Profile Manager"}
            </h2>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                padding: "2px 8px",
                borderRadius: 12,
                background: connected ? "#dcfce7" : "#fef3c7",
                color: connected ? "#166534" : "#92400e",
                border: `1px solid ${connected ? "#bbf7d0" : "#fde68a"}`,
              }}
            >
              {connected ? "✓ Google Connected" : "Not connected"}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
            {connected
              ? `Connected via ${activeAccount || "Google Account"} (${accountType === "secondary_gbp" ? "Store Owner Account" : "Primary Google Services"}). ${dataStatus}`
              : dataStatus}
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {actionError && (
            <span role="alert" style={{ fontSize: 12, color: "#991b1b", fontWeight: 600, background: "#fef2f2", padding: "4px 10px", borderRadius: 4, maxWidth: 420 }}>
              {actionError}
            </span>
          )}
          {saveSuccess && (
            <span style={{ fontSize: 12, color: "#166534", fontWeight: 600, background: "#dcfce7", padding: "4px 10px", borderRadius: 4 }}>
              ✓ {saveSuccess}
            </span>
          )}
          <button
            type="button"
            onClick={handleSaveBusiness}
            disabled={saving}
            style={{
              background: "#0f172a",
              color: "#ffffff",
              border: "none",
              borderRadius: 6,
              padding: "8px 16px",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Saving..." : "Save & Sync to Google"}
          </button>
        </div>
      </div>

      {/* Google Services Hub Accordion/Embed */}
      <GoogleServicesHub compact={true} />

      {/* Sub-Navigation Tabs */}
      <div
        style={{
          display: "flex",
          gap: 6,
          borderBottom: "1px solid #e2e8f0",
          background: "#ffffff",
          padding: "4px 8px 0",
          borderRadius: "8px 8px 0 0",
          overflowX: "auto",
        }}
      >
        {[
          { key: "info", label: "🏢 Business Info & NAP", icon: "🏢" },
          { key: "hours", label: "⏰ Operating & Holiday Hours", icon: "⏰" },
          { key: "reviews", label: `⭐ Reviews & AI Reply (${reviews.length})`, icon: "⭐" },
          { key: "review_boost", label: "🚀 Review Boost & QR", icon: "🚀" },
          { key: "posts", label: `📢 Google Maps Posts (${posts.length})`, icon: "📢" },
          { key: "local_grid", label: "📍 Geo-Grid Map Rank", icon: "📍" },
          { key: "nap_audit", label: "🔍 Website Schema Alignment", icon: "🔍" },
          { key: "insights", label: "📈 Local Performance & Insights", icon: "📈" },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setSubTab(tab.key as SubTab)}
            style={{
              background: subTab === tab.key ? "#f8fafc" : "transparent",
              color: subTab === tab.key ? "#0f172a" : "var(--ink-muted)",
              fontWeight: subTab === tab.key ? 700 : 500,
              border: "none",
              borderBottom: subTab === tab.key ? "2px solid #2563eb" : "2px solid transparent",
              padding: "8px 14px",
              fontSize: 12.5,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Business Information & NAP */}
      {subTab === "info" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 16px" }}>
            Google Maps Business Profile Details
          </h3>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Business Name (as shown on Google Maps)
              </label>
              <input
                type="text"
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Primary Google Category
              </label>
              <input
                type="text"
                value={primaryCategory}
                onChange={(e) => setPrimaryCategory(e.target.value)}
                placeholder="As listed on Google, e.g. Hospital"
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Phone Number (Click-to-call)
              </label>
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Website URL
              </label>
              <input
                type="url"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Appointment / Booking URL
              </label>
              <input
                type="url"
                value={appointmentUrl}
                onChange={(e) => setAppointmentUrl(e.target.value)}
                placeholder="https://"
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                Street Address
              </label>
              <input
                type="text"
                value={street}
                onChange={(e) => setStreet(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                City, State, Zip
              </label>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  type="text"
                  placeholder="City"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  style={{ flex: 2, padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6 }}
                />
                <input
                  type="text"
                  placeholder="State"
                  value={stateCode}
                  onChange={(e) => setStateCode(e.target.value)}
                  style={{ flex: 1, padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6 }}
                />
                <input
                  type="text"
                  placeholder="Zip"
                  value={postalCode}
                  onChange={(e) => setPostalCode(e.target.value)}
                  style={{ flex: 1.5, padding: "8px 10px", fontSize: 13, border: "1px solid #cbd5e1", borderRadius: 6 }}
                />
              </div>
            </div>
          </div>

          {/* Service Areas */}
          <div style={{ marginTop: 20 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
              Service Areas (Cities / Regions Served)
            </label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              {serviceAreas.map((area, idx) => (
                <span
                  key={idx}
                  style={{
                    background: "#f1f5f9",
                    padding: "4px 8px",
                    borderRadius: 4,
                    fontSize: 12,
                    color: "#334155",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  {area}
                  <button
                    type="button"
                    onClick={() => setServiceAreas((prev) => prev.filter((_, i) => i !== idx))}
                    style={{ background: "none", border: "none", color: "var(--ink-muted)", cursor: "pointer", padding: 0 }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, maxWidth: 400 }}>
              <input
                type="text"
                placeholder="Add a city or region"
                value={serviceAreaInput}
                onChange={(e) => setServiceAreaInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && serviceAreaInput.trim()) {
                    e.preventDefault();
                    setServiceAreas((prev) => [...prev, serviceAreaInput.trim()]);
                    setServiceAreaInput("");
                  }
                }}
                style={{ flex: 1, padding: "6px 10px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
              />
              <button
                type="button"
                onClick={() => {
                  if (serviceAreaInput.trim()) {
                    setServiceAreas((prev) => [...prev, serviceAreaInput.trim()]);
                    setServiceAreaInput("");
                  }
                }}
                style={{ background: "#475569", color: "#ffffff", border: "none", borderRadius: 4, padding: "6px 12px", fontSize: 12, cursor: "pointer" }}
              >
                Add Area
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Operating & Holiday Hours */}
      {subTab === "hours" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 14px" }}>
            Regular Weekly Hours
          </h3>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 16px" }}>
            Keep your hours updated to ensure customers don't arrive when you are closed and to maintain Google Maps search eligibility.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 540 }}>
            {daysOfWeek.map((day) => {
              const h = regularHours[day];
              if (!h) {
                return (
                  <div key={day} style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                    <span style={{ fontSize: 13, fontWeight: 600, textTransform: "capitalize", width: 100, color: "#1e293b" }}>{day}</span>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Not listed on Google</span>
                  </div>
                );
              }
              return (
                <div
                  key={day}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: "#f8fafc",
                    borderRadius: 6,
                    border: "1px solid #e2e8f0",
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: 600, textTransform: "capitalize", width: 100, color: "#1e293b" }}>
                    {day}
                  </span>

                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={h.isClosed}
                      onChange={(e) => {
                        const isClosed = e.target.checked;
                        setRegularHours((prev) => ({
                          ...prev,
                          [day]: { ...prev[day], isClosed },
                        }));
                      }}
                    />
                    Closed
                  </label>

                  {!h.isClosed ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <input
                        type="time"
                        value={h.open}
                        onChange={(e) => {
                          const open = e.target.value;
                          setRegularHours((prev) => ({
                            ...prev,
                            [day]: { ...prev[day], open },
                          }));
                        }}
                        style={{ padding: "4px 6px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
                      />
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>to</span>
                      <input
                        type="time"
                        value={h.close}
                        onChange={(e) => {
                          const close = e.target.value;
                          setRegularHours((prev) => ({
                            ...prev,
                            [day]: { ...prev[day], close },
                          }));
                        }}
                        style={{ padding: "4px 6px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
                      />
                    </div>
                  ) : (
                    <span style={{ fontSize: 12, color: "#dc2626", fontWeight: 600 }}>Closed all day</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Holiday / Special Hours */}
          <div style={{ marginTop: 24, borderTop: "1px solid #f1f5f9", paddingTop: 18 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 8px" }}>
              Holiday & Special Hours (Upcoming Closures)
            </h3>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 12px" }}>
              Google flags listings with missing holiday hours as "Hours might differ on holidays". Add upcoming closures to retain customer trust.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 540, marginBottom: 14 }}>
              {specialHours.map((sh) => (
                <div
                  key={sh.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    background: "#fef2f2",
                    borderRadius: 6,
                    border: "1px solid #fecaca",
                  }}
                >
                  <div>
                    <strong style={{ fontSize: 12.5, color: "#991b1b" }}>{sh.occasion}</strong>
                    <div style={{ fontSize: 12, color: "#7f1d1d" }}>
                      {sh.date} — {sh.isClosed ? "Closed" : `Open ${sh.openTime} - ${sh.closeTime}`}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveHoliday(sh.id)}
                    style={{ background: "none", border: "none", color: "#b91c1c", fontSize: 12, cursor: "pointer", fontWeight: 600 }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 8, maxWidth: 540, alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="date"
                value={newHolidayDate}
                onChange={(e) => setNewHolidayDate(e.target.value)}
                style={{ padding: "6px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
              />
              <input
                type="text"
                placeholder="Occasion (e.g. Labor Day, Christmas Eve)"
                value={newHolidayOccasion}
                onChange={(e) => setNewHolidayOccasion(e.target.value)}
                style={{ flex: 1, minWidth: 180, padding: "6px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
              />
              <button
                type="button"
                onClick={handleAddHoliday}
                style={{ background: "#dc2626", color: "#ffffff", border: "none", borderRadius: 4, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
              >
                + Add Closure
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Customer Reviews & AI Reply Engine */}
      {subTab === "reviews" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Google Reviews & AI Responder
              </h3>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 0" }}>
                Responding to Google reviews improves local ranking signals and shows prospective clients you are responsive.
              </p>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 6 }}>
              {[
                { id: "all", label: `All (${reviews.length})` },
                { id: "unreplied", label: `Needs Reply (${reviews.filter((r) => !r.reply).length})` },
                { id: "5star", label: "5-Star" },
                { id: "negative", label: "Critical" },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setReviewFilter(f.id as any)}
                  style={{
                    background: reviewFilter === f.id ? "#0f172a" : "#f1f5f9",
                    color: reviewFilter === f.id ? "#ffffff" : "#475569",
                    border: "none",
                    borderRadius: 4,
                    padding: "4px 10px",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {filteredReviews.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "var(--ink-muted)", fontSize: 13, background: "#f8fafc", borderRadius: 6 }}>
                No reviews match this filter.
              </div>
            ) : (
              filteredReviews.map((rev) => {
                const draft = replyDrafts[rev.id] || "";
                const isReplying = generatingAi === rev.id;
                const isSubmitting = submittingReply === rev.id;

                return (
                  <div
                    key={rev.id}
                    style={{
                      padding: 14,
                      background: "#f8fafc",
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                      <div>
                        <span style={{ fontWeight: 700, color: "#0f172a", fontSize: 13 }}>{rev.reviewer || "Google user"}</span>
                        <span style={{ color: "#d97706", marginLeft: 8, fontSize: 12 }}>
                          {(() => {
                            const n = starsOf(rev.starRating);
                            return n === null ? "no rating" : `${"★".repeat(n)}${"☆".repeat(5 - n)}`;
                          })()}
                        </span>
                      </div>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        {rev.createTime ? new Date(rev.createTime).toLocaleDateString() : ""}
                      </span>
                    </div>

                    <p style={{ fontSize: 12.5, color: "#334155", margin: "0 0 10px", lineHeight: 1.45 }}>
                      {rev.comment ? `"${rev.comment}"` : "(rating only, no comment)"}
                    </p>

                    {/* Existing Reply */}
                    {rev.reply ? (
                      <div style={{ background: "#ffffff", padding: "10px 12px", borderRadius: 6, borderLeft: "3px solid #16a34a", fontSize: 12 }}>
                        <div style={{ fontWeight: 600, color: "#166534", marginBottom: 2 }}>
                          ✓ Replied as Business Owner:
                        </div>
                        <div style={{ color: "#475569" }}>{rev.reply}</div>
                      </div>
                    ) : (
                      /* Unreplied: Show AI generator buttons */
                      <div style={{ marginTop: 8, background: "#ffffff", padding: 12, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: "#dc2626" }}>
                            ⚠️ Unreplied on Google Maps
                          </span>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button
                              type="button"
                              onClick={() => handleGenerateAiReply(rev.id, "professional")}
                              disabled={isReplying}
                              style={{ background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe", padding: "3px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                            >
                              ✨ AI Reply (Professional)
                            </button>
                            <button
                              type="button"
                              onClick={() => handleGenerateAiReply(rev.id, "friendly")}
                              disabled={isReplying}
                              style={{ background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0", padding: "3px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                            >
                              ✨ Friendly
                            </button>
                          </div>
                        </div>

                        <textarea
                          rows={2}
                          value={draft}
                          onChange={(e) => setReplyDrafts((prev) => ({ ...prev, [rev.id]: e.target.value }))}
                          placeholder={isReplying ? "Generating AI draft..." : "Write a reply or click 'AI Reply' above..."}
                          style={{ width: "100%", padding: "6px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4, boxSizing: "border-box", marginBottom: 8 }}
                        />

                        {draft && (
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                            <button
                              type="button"
                              onClick={() => handleSubmitReply(rev.id)}
                              disabled={isSubmitting}
                              style={{ background: "#16a34a", color: "#ffffff", border: "none", borderRadius: 4, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: isSubmitting ? "wait" : "pointer" }}
                            >
                              {isSubmitting ? "Posting..." : "Post Reply to Google Maps"}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Tab: Review Boost & QR Generator */}
      {subTab === "review_boost" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Google Review Growth & QR Code Generator
              </h3>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 0" }}>
                Make it effortless for happy customers to leave 5-star Google reviews from their smartphone.
              </p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, marginBottom: 20 }}>
            {/* Direct Link & QR Code Card */}
            <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "#1e293b", marginBottom: 8 }}>
                Direct Review Link & QR Code
              </div>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 12px", lineHeight: 1.4 }}>
                This direct Google link bypasses searching and opens the 5-star review modal immediately on mobile and desktop.
              </p>

              <div style={{ marginBottom: 12 }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  Google Place ID
                </label>
                <input
                  type="text"
                  value={placeId}
                  onChange={(e) => setPlaceId(e.target.value)}
                  placeholder="ChIJ..."
                  style={{ width: "100%", padding: "6px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4, boxSizing: "border-box" }}
                />
              </div>

              <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
                <input
                  type="text"
                  readOnly
                  value={`https://search.google.com/local/writereview?placeid=${placeId}`}
                  style={{ flex: 1, padding: "6px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4, background: "#ffffff", color: "#334155" }}
                />
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(`https://search.google.com/local/writereview?placeid=${placeId}`);
                    setReviewCopied(true);
                    setTimeout(() => setReviewCopied(false), 2500);
                  }}
                  style={{ background: "#0f172a", color: "#ffffff", border: "none", borderRadius: 4, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                >
                  {reviewCopied ? "✓ Copied" : "Copy Link"}
                </button>
              </div>

              {/* Printable QR Code Graphic */}
              <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
                <div style={{ width: 140, height: 140, background: "#0f172a", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", color: "#ffffff", marginBottom: 10 }}>
                  <svg width="110" height="110" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2 2h8v8H2V2zm2 2v4h4V4H4zm10-2h8v8h-8V2zm2 2v4h4V4h-4zM2 14h8v8H2v-8zm2 2v4h4v-4H4zm14 0h-2v2h2v-2zm-4 0h2v2h-2v-2zm2 4h-2v2h2v-2zm2 0h2v2h-2v-2zm0-2h2v-2h-2v2zm-4-4h2v2h-2v-2zm6 0h2v2h-2v-2z" />
                  </svg>
                </div>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>
                  Scan to Review on Google
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 10px" }}>
                  Point phone camera at code to open Google Maps
                </div>
                <button
                  type="button"
                  onClick={() => window.print()}
                  style={{ background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1", borderRadius: 4, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                >
                  🖨️ Print Counter Sign / Flyer
                </button>
              </div>
            </div>

            {/* Ready-to-Send Request Templates */}
            <div style={{ background: "#ffffff", padding: 16, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: "#1e293b", marginBottom: 8 }}>
                Pre-Written Review Request Templates
              </div>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 12px" }}>
                Send these to customers after a visit. Edit them to fit the business before sending.
              </p>

              <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                {[
                  { id: "sms", label: "📱 SMS / Text" },
                  { id: "email", label: "✉️ Email Follow-Up" },
                  { id: "receipt", label: "🧾 Invoice Footer" },
                ].map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setActiveTemplate(t.id as any)}
                    style={{
                      background: activeTemplate === t.id ? "#0f172a" : "#f1f5f9",
                      color: activeTemplate === t.id ? "#ffffff" : "#475569",
                      border: "none",
                      borderRadius: 4,
                      padding: "4px 10px",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <div style={{ background: "#f8fafc", padding: 12, borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12, color: "#334155", lineHeight: 1.5, marginBottom: 12 }}>
                {activeTemplate === "sms" && (
                  <div>
                    "Hi [Customer Name], thank you for choosing {businessName || "us"}. If you have 30 seconds, could you share a quick review on Google? https://search.google.com/local/writereview?placeid={placeId}"
                  </div>
                )}
                {activeTemplate === "email" && (
                  <div>
                    <strong>Subject: How was your visit?</strong>
                    <br /><br />
                    Dear [Customer Name],<br />
                    Thank you for choosing {businessName || "us"}.<br /><br />
                    Would you take 30 seconds to leave an honest review on Google? Your feedback helps other people decide.<br /><br />
                    👉 Leave a Google Review: https://search.google.com/local/writereview?placeid={placeId}<br /><br />
                    Thank you again for your business!
                  </div>
                )}
                {activeTemplate === "receipt" && (
                  <div>
                    "Thank you for your business! We value your feedback. Please visit https://search.google.com/local/writereview?placeid={placeId} or scan the QR code to review us on Google."
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => {
                  let text = "";
                  if (activeTemplate === "sms") {
                    text = `Hi [Customer Name], thank you for choosing ${businessName || "us"}. If you have 30 seconds, could you share a quick review on Google? https://search.google.com/local/writereview?placeid=${placeId}`;
                  } else if (activeTemplate === "email") {
                    text = `Subject: How was your visit?\n\nDear [Customer Name],\nThank you for choosing ${businessName || "us"}.\n\nWould you take 30 seconds to leave an honest review on Google?\n\n👉 Leave a Google Review: https://search.google.com/local/writereview?placeid=${placeId}\n\nThank you again for your business!`;
                  } else {
                    text = `Thank you for your business! We value your feedback. Please visit https://search.google.com/local/writereview?placeid=${placeId} or scan the QR code to review us on Google.`;
                  }
                  navigator.clipboard.writeText(text);
                  setSaveSuccess("Template copied to clipboard!");
                  setTimeout(() => setSaveSuccess(null), 3000);
                }}
                style={{ background: "#2563eb", color: "#ffffff", border: "none", borderRadius: 4, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
              >
                📋 Copy Template Text
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Google Updates & Posts */}
      {subTab === "posts" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
            Publish Google Maps Updates & Special Offers
          </h3>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 16px" }}>
            Google Posts appear directly on your Google Maps listing and Knowledge Panel, driving clicks and phone inquiries.
          </p>

          {/* Create Post Composer */}
          <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 20 }}>
            <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b", marginBottom: 10 }}>
              Create New Google Post
            </div>

            <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
              {(["STANDARD", "OFFER", "EVENT"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setNewPostType(t)}
                  style={{
                    background: newPostType === t ? "#2563eb" : "#ffffff",
                    color: newPostType === t ? "#ffffff" : "#475569",
                    border: "1px solid #cbd5e1",
                    borderRadius: 4,
                    padding: "4px 10px",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {t === "STANDARD" ? "What's New" : t === "OFFER" ? "Special Offer" : "Event"}
                </button>
              ))}
            </div>

            <textarea
              rows={3}
              value={newPostSummary}
              onChange={(e) => setNewPostSummary(e.target.value)}
              placeholder="What's new at the business?"
              style={{ width: "100%", padding: "8px 10px", fontSize: 12.5, border: "1px solid #cbd5e1", borderRadius: 6, boxSizing: "border-box", marginBottom: 10 }}
            />

            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <span style={{ color: "var(--ink-muted)" }}>Action Button:</span>
                <select
                  value={newPostAction}
                  onChange={(e) => setNewPostAction(e.target.value as any)}
                  style={{ padding: "4px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
                >
                  <option value="LEARN_MORE">Learn More</option>
                  <option value="BOOK">Book Appointment</option>
                  <option value="CALL">Call Now</option>
                </select>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, flex: 1, minWidth: 220 }}>
                <span style={{ color: "var(--ink-muted)" }}>Button Link:</span>
                <input
                  type="url"
                  value={newPostUrl}
                  onChange={(e) => setNewPostUrl(e.target.value)}
                  style={{ flex: 1, padding: "4px 8px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 4 }}
                />
              </div>
            </div>

            <button
              type="button"
              onClick={handlePublishPost}
              disabled={publishingPost || !newPostSummary.trim()}
              style={{
                background: "#0f172a",
                color: "#ffffff",
                border: "none",
                borderRadius: 6,
                padding: "7px 16px",
                fontSize: 12.5,
                fontWeight: 600,
                cursor: publishingPost ? "wait" : "pointer",
              }}
            >
              {publishingPost ? "Publishing to Maps..." : "🚀 Publish to Google Maps"}
            </button>
          </div>

          {/* Active Posts Feed */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Published Posts</div>
            {posts.length === 0 && (
              <div style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>No posts returned by Google.</div>
            )}
            {posts.map((post, i) => (
              <div key={post.name || i} style={{ padding: 12, background: "#ffffff", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, background: "#e0e7ff", color: "#3730a3", padding: "1px 6px", borderRadius: 4 }}>
                    {post.topicType || "POST"}{post.state ? ` · ${post.state}` : ""}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                    {post.createTime ? new Date(post.createTime).toLocaleDateString() : ""}
                  </span>
                </div>
                <p style={{ margin: "0 0 6px", fontSize: 12.5, color: "#334155" }}>{post.summary}</p>
                {post.searchUrl && (
                  <a href={post.searchUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "#2563eb", fontWeight: 600 }}>
                    View on Google
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Geo-Grid. The 3x3 grid, "78% Map Pack Dominance", "Average Local
          Rank #2.6" and three Austin roofing actions were literals shown to every
          client as "Real-Time". Nothing measures a map grid yet, so none is shown. */}
      {subTab === "local_grid" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
            Google Maps Geo-Grid Rank
          </h3>
          <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: 0, lineHeight: 1.6 }}>
            Not measured. A geo-grid needs a Google Maps ranking check from each grid point around the
            business&apos;s location (DataForSEO Maps, a paid call per point) and the listing&apos;s coordinates
            from Google Business Profile. Neither is connected yet, so no ranks are shown.
          </p>
        </div>
      )}

      {/* Tab 5: Website Schema & NAP Alignment */}
      {subTab === "nap_audit" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
            NAP Consistency Audit (Website vs Google Maps)
          </h3>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 16px" }}>
            Search engines compare website schema data with your Google Maps listing. Any mismatch in Name, Address, or Phone lowers local ranking confidence.
          </p>

          {(() => {
            const address = [street, city, stateCode, postalCode, country].filter(Boolean).join(", ");
            const nap: Array<[string, string]> = [
              ["Name (N)", businessName],
              ["Address (A)", address],
              ["Phone (P)", phone],
            ];
            // One object is both shown and copied, so what is pasted is what was reviewed.
            // "@type" is the generic LocalBusiness: this was "RoofingContractor" with
            // addressCountry "US" for every client. Pick the specific schema.org type
            // for the business's category before publishing.
            const schema: Record<string, any> = {
              "@context": "https://schema.org",
              "@type": "LocalBusiness",
              ...(businessName ? { name: businessName } : {}),
              ...(phone ? { telephone: phone } : {}),
              ...(websiteUrl ? { url: websiteUrl } : {}),
              ...(address
                ? {
                    address: {
                      "@type": "PostalAddress",
                      ...(street ? { streetAddress: street } : {}),
                      ...(city ? { addressLocality: city } : {}),
                      ...(stateCode ? { addressRegion: stateCode } : {}),
                      ...(postalCode ? { postalCode } : {}),
                      ...(country ? { addressCountry: country } : {}),
                    },
                  }
                : {}),
              ...(serviceAreas.length ? { areaServed: serviceAreas } : {}),
            };
            const script = `<script type="application/ld+json">\n${JSON.stringify(schema, null, 2)}\n</script>`;
            return (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginBottom: 12 }}>
                  {nap.map(([label, value]) => (
                    <div key={label} style={{ background: "#f8fafc", padding: 14, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" }}>{label}</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: value ? "#0f172a" : "var(--ink-muted)", marginTop: 4 }}>
                        {value || "Not listed on Google"}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>As listed on Google Business Profile</div>
                    </div>
                  ))}
                </div>
                <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 20px" }}>
                  Whether the website shows the same name, address and phone is checked by the Local scan (Local Presence → Run scan).
                </p>

                <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>
                      LocalBusiness Schema (JSON-LD) from the Google listing
                    </div>
                    <button
                      type="button"
                      disabled={!businessName}
                      onClick={() => {
                        navigator.clipboard.writeText(script);
                        setSaveSuccess("Schema copied to clipboard!");
                        setTimeout(() => setSaveSuccess(null), 3000);
                      }}
                      style={{ background: "#2563eb", color: "#ffffff", border: "none", borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: businessName ? "pointer" : "not-allowed", opacity: businessName ? 1 : 0.5 }}
                    >
                      📋 Copy Script
                    </button>
                  </div>
                  {businessName ? (
                    <pre style={{ background: "#0f172a", color: "#e2e8f0", padding: 14, borderRadius: 6, fontSize: 12, overflowX: "auto", lineHeight: 1.5 }}>
                      {script}
                    </pre>
                  ) : (
                    <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: 0 }}>
                      No listing loaded from Google, so there is nothing to build the schema from.
                    </p>
                  )}
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* Tab 6: Performance & Local Insights */}
      {subTab === "insights" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: "0 0 8px 8px", border: "1px solid #e2e8f0", borderTop: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Google Maps & Local Search Insights
              </h3>
              <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 0" }}>
                Verified customer actions and local discovery queries (Last 28 Days).
              </p>
            </div>
          </div>

          {/*
            These four tiles read `insights?.breakdown?.<x>?.count`. The API
            returns a FLAT `metrics` object and has no `breakdown` key at all,
            so the left side was always undefined and 142 / 318 / 784 / 40
            rendered unconditionally — connected or not, real location or not —
            under a heading reading "Verified customer actions". The deltas
            beside them (+14.5%, +22.1%, +19.3%, +33.3%, +18.4%) were string
            literals with nothing behind them.

            Read the real shape, and where Google returned nothing, say so.
            A dash is a fact; 142 is a claim.
          */}
          {(() => {
            const m = insights?.metrics;
            const tiles: Array<[string, number | null | undefined]> = [
              ["\u{1F4DE} Phone Calls", m?.calls],
              ["\u{1F5FA}\uFE0F Direction Requests", m?.directionRequests],
              ["\u{1F310} Website Visits", m?.websiteClicks],
              ["\u{1F4C5} Appointments", m?.bookings],
            ];
            return (
              <>
                {!m ? (
                  <div style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: "0 0 12px", lineHeight: 1.6 }}>
                    {insights?.dataStatus
                      || "No customer-action data for this location. Connect the Google Business Profile to measure calls, direction requests, website visits and bookings."}
                  </div>
                ) : (
                  <div style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: "0 0 12px" }}>
                    {insights?.dataStatus} · {m.period}
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
                  {tiles.map(([label, value]) => (
                    <div key={label} style={{ background: "#f8fafc", padding: 14, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>{label}</div>
                      <div style={{
                        fontSize: 20, fontWeight: 800, marginTop: 4,
                        color: typeof value === "number" ? "#0f172a" : "var(--ink-muted)",
                      }}>
                        {typeof value === "number" ? value.toLocaleString() : "\u2014"}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                        {typeof value === "number" ? "last 28 days" : "not measured"}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            );
          })()}

          {/* Top Search Queries */}
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 8 }}>
              Top Queries Showing Your Google Maps Listing
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {!(insights?.topSearchKeywords || []).length && (
                <div style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>Not returned by the Business Profile API.</div>
              )}
              {(insights?.topSearchKeywords || []).map((k: any, i: number) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: "#f8fafc",
                    borderRadius: 4,
                    fontSize: 12.5,
                  }}
                >
                  <span style={{ fontWeight: 600, color: "#334155" }}>{k.keyword}</span>
                  <span style={{ color: "var(--ink-muted)" }}>{k.impressions} local searches</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
