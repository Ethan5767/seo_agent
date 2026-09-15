"use client";

import React, { useState, useEffect } from "react";
import { GoogleServicesHub } from "./GoogleServicesHub";
import { Panel, StatStrip } from "./Panel";
import styles from "./LocalPresence.module.css";
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
  const uid = `lbm-${React.useId().replace(/:/g, "")}`;
  const saveReasonId = `${uid}-save-reason`;
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

  const tabs: Array<{ key: SubTab; label: string; count?: number }> = [
    { key: "info", label: "Business Info & NAP" },
    { key: "hours", label: "Operating & Holiday Hours" },
    { key: "reviews", label: "Reviews & AI Reply", count: reviews.length },
    { key: "review_boost", label: "Review Boost & QR" },
    { key: "posts", label: "Google Maps Posts", count: posts.length },
    { key: "local_grid", label: "Geo-Grid Map Rank" },
    { key: "nap_audit", label: "Website Schema Alignment" },
    { key: "insights", label: "Local Performance & Insights" },
  ];
  const tabId = (key: string) => `${uid}-tab-${key}`;
  const panelId = `${uid}-tabpanel`;
  const reviewLink = `https://search.google.com/local/writereview?placeid=${placeId}`;

  return (
    <div className={styles.stack}>
      {/* The Google connection comes first: nothing below can sync without it. */}
      <GoogleServicesHub compact={true} />

      <Panel
        title={businessName || "Google Business Profile"}
        subtitle={
          connected
            ? `Connected via ${activeAccount || "Google Account"} (${accountType === "secondary_gbp" ? "Store Owner Account" : "Primary Google Services"}). ${dataStatus}`
            : dataStatus
        }
      >
        <div className={styles.actionRow}>
          <StatusMark state={connected ? "ok" : "warn"} word={connected ? "Google connected" : "Not connected"} />
          <div className={styles.actionEnd}>
            {/* Saving writes to Google, so it cannot run without a connected
                Business Profile. The reason sits beside the disabled button. */}
            {!connected && !loading && (
              <span id={saveReasonId} className={styles.reason}>
                Connect Google Business Profile first
              </span>
            )}
            <button
              type="button"
              className={`btn ${connected ? "btn--primary" : "btn--secondary"}`}
              onClick={handleSaveBusiness}
              disabled={saving || !connected}
              aria-describedby={!connected && !loading ? saveReasonId : undefined}
            >
              {saving ? "Saving..." : "Save & Sync to Google"}
            </button>
          </div>
        </div>

        {(actionError || saveSuccess) && (
          <div className={styles.actionRow}>
            {actionError && (
              <p role="alert" className={`${styles.notice} ${styles.noticeBad}`}>
                {actionError}
              </p>
            )}
            {saveSuccess && (
              <p role="status" className={`${styles.notice} ${styles.noticeOk}`}>
                {saveSuccess}
              </p>
            )}
          </div>
        )}

        {/* Sub-Navigation Tabs */}
        <div className="audit-tabs" role="tablist" aria-label="Business Profile sections">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              id={tabId(tab.key)}
              type="button"
              role="tab"
              aria-selected={subTab === tab.key}
              aria-controls={panelId}
              tabIndex={subTab === tab.key ? 0 : -1}
              className="audit-tabs__tab"
              onClick={() => setSubTab(tab.key)}
              onKeyDown={(e) => {
                if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
                e.preventDefault();
                const i = tabs.findIndex((t) => t.key === tab.key);
                const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
                setSubTab(next.key);
                document.getElementById(tabId(next.key))?.focus();
              }}
            >
              {tab.label}
              {typeof tab.count === "number" && <span className="audit-tabs__count">{tab.count}</span>}
            </button>
          ))}
        </div>

        <div id={panelId} role="tabpanel" aria-labelledby={tabId(subTab)} className={styles.section}>
          {/* Tab 1: Business Information & NAP */}
          {subTab === "info" && (
            <>
              <h4 className={styles.sectionTitle}>Google Maps Business Profile Details</h4>

              <div className={styles.formGrid}>
                <Field label="Business Name (as shown on Google Maps)">
                  {(id) => (
                    <input id={id} type="text" className={styles.input} value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
                  )}
                </Field>

                <Field label="Primary Google Category">
                  {(id) => (
                    <input
                      id={id}
                      type="text"
                      className={styles.input}
                      value={primaryCategory}
                      onChange={(e) => setPrimaryCategory(e.target.value)}
                      placeholder="As listed on Google, e.g. Hospital"
                    />
                  )}
                </Field>

                <Field label="Phone Number (Click-to-call)">
                  {(id) => (
                    <input id={id} type="tel" className={styles.input} value={phone} onChange={(e) => setPhone(e.target.value)} />
                  )}
                </Field>

                <Field label="Website URL">
                  {(id) => (
                    <input id={id} type="url" className={styles.input} value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} />
                  )}
                </Field>

                <Field label="Appointment / Booking URL">
                  {(id) => (
                    <input
                      id={id}
                      type="url"
                      className={styles.input}
                      value={appointmentUrl}
                      onChange={(e) => setAppointmentUrl(e.target.value)}
                      placeholder="https://"
                    />
                  )}
                </Field>

                <Field label="Street Address">
                  {(id) => (
                    <input id={id} type="text" className={styles.input} value={street} onChange={(e) => setStreet(e.target.value)} />
                  )}
                </Field>

                {/* One visible group label; each input still has its own label. */}
                <fieldset className={`${styles.field} ${styles.fieldFull}`}>
                  <legend className={styles.label} style={{ marginBottom: "var(--space-1)" }}>City, State, Zip</legend>
                  <div className={styles.addressGroup}>
                    <label htmlFor={`${uid}-city`} className="visually-hidden">City</label>
                    <input id={`${uid}-city`} type="text" className={styles.input} placeholder="City" value={city} onChange={(e) => setCity(e.target.value)} />
                    <label htmlFor={`${uid}-state`} className="visually-hidden">State</label>
                    <input id={`${uid}-state`} type="text" className={styles.input} placeholder="State" value={stateCode} onChange={(e) => setStateCode(e.target.value)} />
                    <label htmlFor={`${uid}-zip`} className="visually-hidden">Zip</label>
                    <input id={`${uid}-zip`} type="text" className={styles.input} placeholder="Zip" value={postalCode} onChange={(e) => setPostalCode(e.target.value)} />
                  </div>
                </fieldset>
              </div>

              {/* Service Areas */}
              <div className={`${styles.section} ${styles.divider}`}>
                <h4 className={styles.sectionTitle}>Service Areas (Cities / Regions Served)</h4>
                {serviceAreas.length > 0 ? (
                  <ul className={styles.chips}>
                    {serviceAreas.map((area, idx) => (
                      <li key={idx} className={styles.chip}>
                        {area}
                        <button
                          type="button"
                          className={styles.chipRemove}
                          aria-label={`Remove ${area}`}
                          onClick={() => setServiceAreas((prev) => prev.filter((_, i) => i !== idx))}
                        >
                          <IconClose />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.lede} style={{ margin: 0 }}>No service areas listed.</p>
                )}
                <div className={styles.inline} style={{ maxWidth: 520 }}>
                  <Field label="Add a service area" className={styles.fieldGrow}>
                    {(id) => (
                      <input
                        id={id}
                        type="text"
                        className={styles.input}
                        placeholder="A city or region"
                        value={serviceAreaInput}
                        onChange={(e) => setServiceAreaInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && serviceAreaInput.trim()) {
                            e.preventDefault();
                            setServiceAreas((prev) => [...prev, serviceAreaInput.trim()]);
                            setServiceAreaInput("");
                          }
                        }}
                      />
                    )}
                  </Field>
                  <button
                    type="button"
                    className={`btn btn--secondary ${styles.blockNarrow}`}
                    onClick={() => {
                      if (serviceAreaInput.trim()) {
                        setServiceAreas((prev) => [...prev, serviceAreaInput.trim()]);
                        setServiceAreaInput("");
                      }
                    }}
                  >
                    Add Area
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Tab 2: Operating & Holiday Hours */}
          {subTab === "hours" && (
            <>
              <div>
                <h4 className={styles.sectionTitle}>Regular Weekly Hours</h4>
                <p className={styles.lede}>
                  Keep your hours updated to ensure customers don&apos;t arrive when you are closed and to maintain Google Maps search eligibility.
                </p>
              </div>

              <ul className={styles.rowList}>
                {daysOfWeek.map((day) => {
                  const h = regularHours[day];
                  if (!h) {
                    return (
                      <li key={day} className={styles.hoursRow}>
                        <span className={styles.day}>{day}</span>
                        <span className={styles.reason} style={{ gridColumn: "2 / -1", justifySelf: "end" }}>Not listed on Google</span>
                      </li>
                    );
                  }
                  return (
                    <li key={day} className={styles.hoursRow}>
                      <span className={styles.day}>{day}</span>

                      <label className={styles.checkbox}>
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
                        <div className={styles.timeRange}>
                          <label htmlFor={`${uid}-${day}-open`} className="visually-hidden">{`${day} opens at`}</label>
                          <input
                            id={`${uid}-${day}-open`}
                            type="time"
                            className={`${styles.input} ${styles.inputAuto}`}
                            value={h.open}
                            onChange={(e) => {
                              const open = e.target.value;
                              setRegularHours((prev) => ({
                                ...prev,
                                [day]: { ...prev[day], open },
                              }));
                            }}
                          />
                          <span aria-hidden="true">to</span>
                          <label htmlFor={`${uid}-${day}-close`} className="visually-hidden">{`${day} closes at`}</label>
                          <input
                            id={`${uid}-${day}-close`}
                            type="time"
                            className={`${styles.input} ${styles.inputAuto}`}
                            value={h.close}
                            onChange={(e) => {
                              const close = e.target.value;
                              setRegularHours((prev) => ({
                                ...prev,
                                [day]: { ...prev[day], close },
                              }));
                            }}
                          />
                        </div>
                      ) : (
                        <span className={styles.timeRange} style={{ color: "var(--bad)", fontWeight: 600 }}>Closed all day</span>
                      )}
                    </li>
                  );
                })}
              </ul>

              {/* Holiday / Special Hours */}
              <div className={`${styles.section} ${styles.divider}`}>
                <div>
                  <h4 className={styles.sectionTitle}>Holiday & Special Hours (Upcoming Closures)</h4>
                  <p className={styles.lede}>
                    Google flags listings with missing holiday hours as &quot;Hours might differ on holidays&quot;. Add upcoming closures to retain customer trust.
                  </p>
                </div>

                {specialHours.length > 0 && (
                  <ul className={styles.rowList}>
                    {specialHours.map((sh) => (
                      <li key={sh.id} className={styles.closureRow}>
                        <div style={{ minWidth: 0 }}>
                          <strong style={{ color: "var(--ink)" }}>{sh.occasion}</strong>
                          <div className={styles.reason}>
                            {sh.date}: {sh.isClosed ? "Closed" : `Open ${sh.openTime} - ${sh.closeTime}`}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          style={{ color: "var(--bad)" }}
                          aria-label={`Remove ${sh.occasion} closure`}
                          onClick={() => handleRemoveHoliday(sh.id)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <div className={styles.inline} style={{ maxWidth: 640 }}>
                  <Field label="Closure date">
                    {(id) => (
                      <input id={id} type="date" className={`${styles.input} ${styles.inputAuto}`} value={newHolidayDate} onChange={(e) => setNewHolidayDate(e.target.value)} />
                    )}
                  </Field>
                  <Field label="Occasion" className={styles.fieldGrow}>
                    {(id) => (
                      <input
                        id={id}
                        type="text"
                        className={styles.input}
                        placeholder="e.g. Labor Day, Christmas Eve"
                        value={newHolidayOccasion}
                        onChange={(e) => setNewHolidayOccasion(e.target.value)}
                      />
                    )}
                  </Field>
                  <button type="button" className={`btn btn--secondary ${styles.blockNarrow}`} onClick={handleAddHoliday}>
                    <IconPlus />
                    Add Closure
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Tab 3: Customer Reviews & AI Reply Engine */}
          {subTab === "reviews" && (
            <>
              <div className={styles.sectionHead}>
                <div>
                  <h4 className={styles.sectionTitle}>Google Reviews & AI Responder</h4>
                  <p className={styles.lede}>
                    Responding to Google reviews improves local ranking signals and shows prospective clients you are responsive.
                  </p>
                </div>

                {/* Filters */}
                <div className={`segmented ${styles.segmentedWrap}`} role="group" aria-label="Filter reviews">
                  {[
                    { id: "all", label: `All (${reviews.length})` },
                    { id: "unreplied", label: `Needs Reply (${reviews.filter((r) => !r.reply).length})` },
                    { id: "5star", label: "5-Star" },
                    { id: "negative", label: "Critical" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      aria-pressed={reviewFilter === f.id}
                      onClick={() => setReviewFilter(f.id as any)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredReviews.length === 0 ? (
                <div className="audit-empty">
                  <p>No reviews match this filter.</p>
                </div>
              ) : (
                <ul className={styles.plainList}>
                  {filteredReviews.map((rev) => {
                    const draft = replyDrafts[rev.id] || "";
                    const isReplying = generatingAi === rev.id;
                    const isSubmitting = submittingReply === rev.id;
                    const n = starsOf(rev.starRating);

                    return (
                      <li key={rev.id} className={styles.item}>
                        <div className={styles.itemHead}>
                          <span>
                            <strong style={{ color: "var(--ink)" }}>{rev.reviewer || "Google user"}</strong>{" "}
                            {n === null ? (
                              <span className={styles.reason}>no rating</span>
                            ) : (
                              <span className={styles.stars} role="img" aria-label={`${n} of 5 stars`}>
                                {`${"★".repeat(n)}${"☆".repeat(5 - n)}`}
                              </span>
                            )}
                          </span>
                          <span className={styles.reason}>
                            {rev.createTime ? new Date(rev.createTime).toLocaleDateString() : ""}
                          </span>
                        </div>

                        <p className={styles.itemBody}>
                          {rev.comment ? `"${rev.comment}"` : "(rating only, no comment)"}
                        </p>

                        {/* Existing Reply */}
                        {rev.reply ? (
                          <div className={styles.reply}>
                            <StatusMark state="ok" word="Replied as Business Owner" />
                            <div style={{ marginTop: "var(--space-1)" }}>{rev.reply}</div>
                          </div>
                        ) : (
                          /* Unreplied: Show AI generator buttons */
                          <div className={`${styles.card} ${styles.cardPlain}`}>
                            <div className={styles.sectionHead}>
                              <StatusMark state="warn" word="Unreplied on Google Maps" />
                              <div className={styles.inline}>
                                <button
                                  type="button"
                                  className="btn btn--secondary btn--sm"
                                  onClick={() => handleGenerateAiReply(rev.id, "professional")}
                                  disabled={isReplying}
                                >
                                  AI Reply (Professional)
                                </button>
                                <button
                                  type="button"
                                  className="btn btn--secondary btn--sm"
                                  onClick={() => handleGenerateAiReply(rev.id, "friendly")}
                                  disabled={isReplying}
                                >
                                  AI Reply (Friendly)
                                </button>
                              </div>
                            </div>

                            <label htmlFor={`${uid}-reply-${rev.id}`} className="visually-hidden">
                              {`Reply to ${rev.reviewer || "Google user"}`}
                            </label>
                            <textarea
                              id={`${uid}-reply-${rev.id}`}
                              rows={3}
                              className={`${styles.input} ${styles.textarea}`}
                              value={draft}
                              onChange={(e) => setReplyDrafts((prev) => ({ ...prev, [rev.id]: e.target.value }))}
                              placeholder={isReplying ? "Generating AI draft..." : "Write a reply or draft one with AI Reply above..."}
                            />

                            {draft && (
                              <div className={styles.actionRow}>
                                <div className={styles.actionEnd}>
                                  <button
                                    type="button"
                                    className="btn btn--secondary btn--sm"
                                    onClick={() => handleSubmitReply(rev.id)}
                                    disabled={isSubmitting}
                                  >
                                    {isSubmitting ? "Posting..." : "Post Reply to Google Maps"}
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}

          {/* Tab: Review Boost & QR Generator */}
          {subTab === "review_boost" && (
            <>
              <div>
                <h4 className={styles.sectionTitle}>Google Review Growth & QR Code Generator</h4>
                <p className={styles.lede}>
                  Make it effortless for happy customers to leave 5-star Google reviews from their smartphone.
                </p>
              </div>

              <div className={styles.cardGrid}>
                {/* Direct Link & QR Code Card */}
                <div className={styles.card}>
                  <div>
                    <h5 className={styles.cardTitle}>Direct Review Link & QR Code</h5>
                    <p className={styles.lede}>
                      This direct Google link bypasses searching and opens the 5-star review modal immediately on mobile and desktop.
                    </p>
                  </div>

                  <Field label="Google Place ID">
                    {(id) => (
                      <input id={id} type="text" className={styles.input} value={placeId} onChange={(e) => setPlaceId(e.target.value)} placeholder="ChIJ..." />
                    )}
                  </Field>

                  <div className={styles.inline}>
                    <Field label="Review link" className={styles.fieldGrow}>
                      {(id) => <input id={id} type="text" readOnly className={styles.input} value={reviewLink} />}
                    </Field>
                    <button
                      type="button"
                      className={`btn btn--secondary ${styles.blockNarrow}`}
                      onClick={() => {
                        navigator.clipboard.writeText(reviewLink);
                        setReviewCopied(true);
                        setTimeout(() => setReviewCopied(false), 2500);
                      }}
                    >
                      {reviewCopied ? "Copied" : "Copy Link"}
                    </button>
                  </div>

                  {/* Printable QR Code Graphic */}
                  <div className={styles.qr}>
                    <div className={styles.qrMark}>
                      <svg width="110" height="110" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M2 2h8v8H2V2zm2 2v4h4V4H4zm10-2h8v8h-8V2zm2 2v4h4V4h-4zM2 14h8v8H2v-8zm2 2v4h4v-4H4zm14 0h-2v2h2v-2zm-4 0h2v2h-2v-2zm2 4h-2v2h2v-2zm2 0h2v2h-2v-2zm0-2h2v-2h-2v2zm-4-4h2v2h-2v-2zm6 0h2v2h-2v-2z" />
                      </svg>
                    </div>
                    <strong style={{ fontSize: "var(--text-sm)", color: "var(--ink)" }}>Scan to Review on Google</strong>
                    <span className={styles.reason}>Point phone camera at code to open Google Maps</span>
                    <button type="button" className="btn btn--secondary btn--sm" onClick={() => window.print()}>
                      <IconPrinter />
                      Print Counter Sign / Flyer
                    </button>
                  </div>
                </div>

                {/* Ready-to-Send Request Templates */}
                <div className={`${styles.card} ${styles.cardPlain}`}>
                  <div>
                    <h5 className={styles.cardTitle}>Pre-Written Review Request Templates</h5>
                    <p className={styles.lede}>
                      Send these to customers after a visit. Edit them to fit the business before sending.
                    </p>
                  </div>

                  <div className={`segmented ${styles.segmentedWrap}`} role="group" aria-label="Template">
                    {[
                      { id: "sms", label: "SMS / Text" },
                      { id: "email", label: "Email Follow-Up" },
                      { id: "receipt", label: "Invoice Footer" },
                    ].map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        aria-pressed={activeTemplate === t.id}
                        onClick={() => setActiveTemplate(t.id as any)}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>

                  <div className={styles.template}>
                    {activeTemplate === "sms" && (
                      <div>
                        &quot;Hi [Customer Name], thank you for choosing {businessName || "us"}. If you have 30 seconds, could you share a quick review on Google? {reviewLink}&quot;
                      </div>
                    )}
                    {activeTemplate === "email" && (
                      <div>
                        <strong>Subject: How was your visit?</strong>
                        <br /><br />
                        Dear [Customer Name],<br />
                        Thank you for choosing {businessName || "us"}.<br /><br />
                        Would you take 30 seconds to leave an honest review on Google? Your feedback helps other people decide.<br /><br />
                        Leave a Google Review: {reviewLink}<br /><br />
                        Thank you again for your business!
                      </div>
                    )}
                    {activeTemplate === "receipt" && (
                      <div>
                        &quot;Thank you for your business! We value your feedback. Please visit {reviewLink} or scan the QR code to review us on Google.&quot;
                      </div>
                    )}
                  </div>

                  <div>
                    <button
                      type="button"
                      className={`btn btn--secondary ${styles.blockNarrow}`}
                      onClick={() => {
                        let text = "";
                        if (activeTemplate === "sms") {
                          text = `Hi [Customer Name], thank you for choosing ${businessName || "us"}. If you have 30 seconds, could you share a quick review on Google? https://search.google.com/local/writereview?placeid=${placeId}`;
                        } else if (activeTemplate === "email") {
                          text = `Subject: How was your visit?\n\nDear [Customer Name],\nThank you for choosing ${businessName || "us"}.\n\nWould you take 30 seconds to leave an honest review on Google?\n\nLeave a Google Review: https://search.google.com/local/writereview?placeid=${placeId}\n\nThank you again for your business!`;
                        } else {
                          text = `Thank you for your business! We value your feedback. Please visit https://search.google.com/local/writereview?placeid=${placeId} or scan the QR code to review us on Google.`;
                        }
                        navigator.clipboard.writeText(text);
                        setSaveSuccess("Template copied to clipboard!");
                        setTimeout(() => setSaveSuccess(null), 3000);
                      }}
                    >
                      <IconCopy />
                      Copy Template Text
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Tab 4: Google Updates & Posts */}
          {subTab === "posts" && (
            <>
              <div>
                <h4 className={styles.sectionTitle}>Publish Google Maps Updates & Special Offers</h4>
                <p className={styles.lede}>
                  Google Posts appear directly on your Google Maps listing and Knowledge Panel, driving clicks and phone inquiries.
                </p>
              </div>

              {/* Create Post Composer */}
              <div className={styles.card}>
                <h5 className={styles.cardTitle}>Create New Google Post</h5>

                <div className={`segmented ${styles.segmentedWrap}`} role="group" aria-label="Post type">
                  {(["STANDARD", "OFFER", "EVENT"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      aria-pressed={newPostType === t}
                      onClick={() => setNewPostType(t)}
                    >
                      {t === "STANDARD" ? "What's New" : t === "OFFER" ? "Special Offer" : "Event"}
                    </button>
                  ))}
                </div>

                <Field label="Post text">
                  {(id) => (
                    <textarea
                      id={id}
                      rows={3}
                      className={`${styles.input} ${styles.textarea}`}
                      value={newPostSummary}
                      onChange={(e) => setNewPostSummary(e.target.value)}
                      placeholder="What's new at the business?"
                    />
                  )}
                </Field>

                <div className={styles.formGrid}>
                  <Field label="Action button">
                    {(id) => (
                      <select id={id} className={styles.input} value={newPostAction} onChange={(e) => setNewPostAction(e.target.value as any)}>
                        <option value="LEARN_MORE">Learn More</option>
                        <option value="BOOK">Book Appointment</option>
                        <option value="CALL">Call Now</option>
                      </select>
                    )}
                  </Field>

                  <Field label="Button link">
                    {(id) => (
                      <input id={id} type="url" className={styles.input} value={newPostUrl} onChange={(e) => setNewPostUrl(e.target.value)} />
                    )}
                  </Field>
                </div>

                <div>
                  <button
                    type="button"
                    className={`btn btn--secondary ${styles.blockNarrow}`}
                    onClick={handlePublishPost}
                    disabled={publishingPost || !newPostSummary.trim()}
                  >
                    {publishingPost ? "Publishing to Maps..." : "Publish to Google Maps"}
                  </button>
                </div>
              </div>

              {/* Active Posts Feed */}
              <div className={styles.section}>
                <h5 className={styles.cardTitle}>Published Posts</h5>
                {posts.length === 0 ? (
                  <div className="audit-empty">
                    <p>No posts returned by Google.</p>
                  </div>
                ) : (
                  <ul className={styles.plainList}>
                    {posts.map((post, i) => (
                      <li key={post.name || i} className={`${styles.item} ${styles.cardPlain}`}>
                        <div className={styles.itemHead}>
                          <span className={styles.tag}>
                            {post.topicType || "POST"}{post.state ? ` · ${post.state}` : ""}
                          </span>
                          <span className={styles.reason}>
                            {post.createTime ? new Date(post.createTime).toLocaleDateString() : ""}
                          </span>
                        </div>
                        <p className={styles.itemBody}>{post.summary}</p>
                        {post.searchUrl && (
                          <a href={post.searchUrl} target="_blank" rel="noreferrer" className="link" style={{ fontSize: "var(--text-sm)", alignSelf: "flex-start" }}>
                            View on Google
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}

          {/* Tab: Geo-Grid. The 3x3 grid, "78% Map Pack Dominance", "Average Local
              Rank #2.6" and three Austin roofing actions were literals shown to every
              client as "Real-Time". Nothing measures a map grid yet, so none is shown. */}
          {subTab === "local_grid" && (
            <>
              <h4 className={styles.sectionTitle}>Google Maps Geo-Grid Rank</h4>
              <div className="audit-empty">
                <p>
                  Not measured. A geo-grid needs a Google Maps ranking check from each grid point around the
                  business&apos;s location (DataForSEO Maps, a paid call per point) and the listing&apos;s coordinates
                  from Google Business Profile. Neither is connected yet, so no ranks are shown.
                </p>
              </div>
            </>
          )}

          {/* Tab 5: Website Schema & NAP Alignment */}
          {subTab === "nap_audit" && (
            <>
              <div>
                <h4 className={styles.sectionTitle}>NAP Consistency Audit (Website vs Google Maps)</h4>
                <p className={styles.lede}>
                  Search engines compare website schema data with your Google Maps listing. Any mismatch in Name, Address, or Phone lowers local ranking confidence.
                </p>
              </div>

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
                    <dl className={styles.kvGrid}>
                      {nap.map(([label, value]) => (
                        <div key={label} className={styles.card} style={{ gap: 0 }}>
                          <dt className={styles.label}>{label}</dt>
                          <dd className={styles.kvValue} style={value ? undefined : { color: "var(--ink-muted)" }}>
                            {value || "Not listed on Google"}
                          </dd>
                          <dd className={styles.kvSub}>As listed on Google Business Profile</dd>
                        </div>
                      ))}
                    </dl>
                    <p className={styles.lede} style={{ margin: 0 }}>
                      Whether the website shows the same name, address and phone is checked by the Local scan (Local Presence → Run scan).
                    </p>

                    <div className={`${styles.section} ${styles.divider}`}>
                      <div className={styles.sectionHead}>
                        <h5 className={styles.cardTitle}>LocalBusiness Schema (JSON-LD) from the Google listing</h5>
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          disabled={!businessName}
                          onClick={() => {
                            navigator.clipboard.writeText(script);
                            setSaveSuccess("Schema copied to clipboard!");
                            setTimeout(() => setSaveSuccess(null), 3000);
                          }}
                        >
                          <IconCopy />
                          Copy Script
                        </button>
                      </div>
                      {businessName ? (
                        <pre className={styles.code}>{script}</pre>
                      ) : (
                        <div className="audit-empty">
                          <p>No listing loaded from Google, so there is nothing to build the schema from.</p>
                        </div>
                      )}
                    </div>
                  </>
                );
              })()}
            </>
          )}

          {/* Tab 6: Performance & Local Insights */}
          {subTab === "insights" && (
            <>
              <div>
                <h4 className={styles.sectionTitle}>Google Maps & Local Search Insights</h4>
                <p className={styles.lede}>
                  Verified customer actions and local discovery queries (Last 28 Days).
                </p>
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
                  ["Phone Calls", m?.calls],
                  ["Direction Requests", m?.directionRequests],
                  ["Website Visits", m?.websiteClicks],
                  ["Appointments", m?.bookings],
                ];
                return (
                  <>
                    <p className={styles.lede} style={{ margin: 0 }}>
                      {!m
                        ? insights?.dataStatus
                          || "No customer-action data for this location. Connect the Google Business Profile to measure calls, direction requests, website visits and bookings."
                        : `${insights?.dataStatus} · ${m.period}`}
                    </p>
                    <StatStrip
                      label="Customer actions"
                      stats={tiles.map(([label, value]) => ({
                        label,
                        value: typeof value === "number" ? value.toLocaleString() : "—",
                        tone: typeof value === "number" ? undefined : "var(--ink-muted)",
                        sub: typeof value === "number" ? "last 28 days" : "not measured",
                      }))}
                    />
                  </>
                );
              })()}

              {/* Top Search Queries */}
              <div className={styles.section}>
                <h5 className={styles.cardTitle}>Top Queries Showing Your Google Maps Listing</h5>
                {!(insights?.topSearchKeywords || []).length ? (
                  <div className="audit-empty">
                    <p>Not returned by the Business Profile API.</p>
                  </div>
                ) : (
                  <ul className={styles.plainList}>
                    {(insights?.topSearchKeywords || []).map((k: any, i: number) => (
                      <li key={i} className={styles.queryRow}>
                        <span style={{ fontWeight: 600, color: "var(--ink-body)", overflowWrap: "anywhere" }}>{k.keyword}</span>
                        <span className={styles.reason}>{k.impressions} local searches</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}

/** A labelled field: the label is a real `<label htmlFor>`, never a placeholder. */
function Field({
  label, className, children,
}: {
  label: string;
  className?: string;
  children: (id: string) => React.ReactNode;
}) {
  const id = `field-${React.useId().replace(/:/g, "")}`;
  return (
    <div className={`${styles.field}${className ? ` ${className}` : ""}`}>
      <label htmlFor={id} className={styles.label}>{label}</label>
      {children(id)}
    </div>
  );
}

/** Status as an icon plus a word, on the shared `.sev` classes (DESIGN.md §2.5). */
function StatusMark({ state, word }: { state: "ok" | "warn"; word: string }) {
  return (
    <span className={state === "ok" ? "sev sev--ok" : "sev sev--warn"} style={{ whiteSpace: "normal" }}>
      <span className="sev__glyph" aria-hidden="true">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ display: "block" }}>
          {state === "ok"
            ? <polyline points="20 6 9 17 4 12" />
            : <><line x1="12" y1="6" x2="12" y2="13" /><line x1="12" y1="18" x2="12.01" y2="18" /></>}
        </svg>
      </span>
      {word}
    </span>
  );
}

/* Line icons, 24x24, stroke currentColor (matches components/dashboard/primitives.tsx). */
function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}
function IconClose() {
  return <Svg><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></Svg>;
}
function IconPlus() {
  return <Svg><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></Svg>;
}
function IconCopy() {
  return <Svg><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></Svg>;
}
function IconPrinter() {
  return <Svg><polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" /></Svg>;
}
