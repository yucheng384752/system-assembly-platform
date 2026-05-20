// src/App.tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadPage } from "./pages/UploadPage";
import { QueryPage } from "./pages/QueryPage";
import { RegisterPage } from "./pages/RegisterPage";
import { AdminPage } from "./pages/AdminPage";
import { ManagerPage } from "./pages/ManagerPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ToastContainer } from "./components/common/ToastContainer";
import LogViewer from "./components/SimpleLogViewer";
import "./styles/app.css";

import { getAdminApiKeyValue, isAdminUnlockedInSession } from "./services/adminAuth";
import { getFontScaleId, setFontScaleId, type FontScaleId } from "./services/a11y";

type MainTab = "upload" | "query" | "analysis" | "register" | "manager" | "admin" | "logs";

function App() {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<MainTab>("register");

  const [fontScale, setFontScale] = useState<FontScaleId>(() => getFontScaleId());

  const currentLang = useMemo(() => {
    const raw = (i18n.resolvedLanguage || i18n.language || 'zh-TW').toLowerCase();
    if (raw === 'zh-tw' || raw === 'zh_tw') return 'zh-TW';
    if (raw.startsWith('zh')) return 'zh-TW';
    return 'en';
  }, [i18n.language, i18n.resolvedLanguage]);

  const [adminUnlocked, setAdminUnlocked] = useState<boolean>(() => Boolean(getAdminApiKeyValue()) && isAdminUnlockedInSession());
  const canShowAdmin = useMemo(() => adminUnlocked, [adminUnlocked]);

  const [actorRole, setActorRole] = useState<string | null>(null);
  const canShowManager = useMemo(() => {
    const r = String(actorRole || '').trim();
    return r === 'manager';
  }, [actorRole]);

  useEffect(() => {
    // If admin key is cleared, force-exit admin tab.
    if (!canShowAdmin && tab === "admin") {
      setTab("register");
    }
  }, [canShowAdmin, tab]);

  useEffect(() => {
    // If role is not privileged, force-exit manager tab.
    if (!canShowManager && tab === "manager") {
      setTab("register");
    }
  }, [canShowManager, tab]);

  return (
    <div className="app-root">
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '12px' }}>
          <div>
            <h1 className="app-title">{t('app.title')}</h1>
            <p className="app-subtitle">{t('app.subtitle')}</p>
          </div>

          <div className="app-lang-switch" aria-label={t('language.label')}>
            <span className="app-lang-label">{t('language.label')}</span>
            <div className="app-lang-tabs" role="tablist" aria-label={t('language.label')}>
              <button
                type="button"
                role="tab"
                aria-selected={currentLang === 'zh-TW'}
                className={`app-lang-tab ${currentLang === 'zh-TW' ? 'is-active' : ''}`}
                onClick={() => i18n.changeLanguage('zh-TW')}
              >
                {t('language.zhTW')}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={currentLang === 'en'}
                className={`app-lang-tab ${currentLang === 'en' ? 'is-active' : ''}`}
                onClick={() => i18n.changeLanguage('en')}
              >
                {t('language.en')}
              </button>
            </div>
          </div>

          <div className="app-a11y" aria-label={t('a11y.fontSize.label')}>
            <span className="app-a11y-label">{t('a11y.fontSize.label')}</span>
            <select
              className="app-a11y-select"
              value={fontScale}
              onChange={(e) => {
                const next = (e.target.value || 'md') as FontScaleId
                setFontScale(next)
                setFontScaleId(next)
              }}
            >
              <option value="sm">{t('a11y.fontSize.small')}</option>
              <option value="md">{t('a11y.fontSize.medium')}</option>
              <option value="lg">{t('a11y.fontSize.large')}</option>
            </select>
          </div>
        </div>

        <div className="app-main-tabs">
          <button
            className={`app-main-tab ${tab === "register" ? "is-active" : ""}`}
            onClick={() => setTab("register")}
          >
            {t('tabs.register')}
          </button>
          <button
            className={`app-main-tab ${tab === "upload" ? "is-active" : ""}`}
            onClick={() => setTab("upload")}
          >
            {t('tabs.upload')}
          </button>
          <button
            className={`app-main-tab ${tab === "query" ? "is-active" : ""}`}
            onClick={() => setTab("query")}
          >
            {t('tabs.query')}
          </button>
          <button
            className={`app-main-tab ${tab === "analysis" ? "is-active" : ""}`}
            onClick={() => setTab("analysis")}
          >
            {t('tabs.analysis')}
          </button>
          {canShowManager ? (
            <button
              className={`app-main-tab ${tab === "manager" ? "is-active" : ""}`}
              onClick={() => setTab("manager")}
            >
              {t('tabs.manager')}
            </button>
          ) : null}
          {canShowAdmin ? (
            <button
              className={`app-main-tab ${tab === "admin" ? "is-active" : ""}`}
              onClick={() => setTab("admin")}
            >
              {t('tabs.admin')}
            </button>
          ) : null}
          {/* <button
            className={`app-main-tab ${tab === "logs" ? "is-active" : ""}`}
            onClick={() => setTab("logs")}
          >
            系統日誌
          </button> */}
          {/* <button
            className={`app-main-tab ${tab === "analysis" ? "is-active" : ""}`}
            onClick={() => setTab("analysis")}
          >
            系統日誌
          </button> */}
        </div>
      </header>

      <main className="app-main">
        {tab === "register" ? (
          <RegisterPage
            onAdminUnlocked={(ok) => setAdminUnlocked(Boolean(ok))}
            onWhoamiChanged={(w) => setActorRole(w?.actor_role ?? null)}
          />
        ) : tab === "upload" ? (
          <UploadPage />
        ) : tab === "query" ? (
          <QueryPage />
        ) : tab === "analysis" ? (
          <AnalyticsPage />
        ) : tab === "manager" ? (
          <ManagerPage />
        ) : tab === "admin" ? (
          <AdminPage onAdminLocked={() => setAdminUnlocked(false)} onAdminUnlocked={() => setAdminUnlocked(true)} />
        ) : (
          <LogViewer />
        )}
      </main>

      <ToastContainer />
    </div>
  );
}

export default App;
