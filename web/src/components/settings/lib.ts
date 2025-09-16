import {
  CombinedSettings,
  EnterpriseSettings,
  GatingType,
  Settings,
} from "@/app/admin/settings/interfaces";
import {
  CUSTOM_ANALYTICS_ENABLED,
  HOST_URL,
  SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED,
} from "@/lib/constants";
import { fetchSS } from "@/lib/utilsSS";
import { getWebVersion } from "@/lib/version";

export enum SettingsError {
  OTHER = "OTHER",
}

export async function fetchStandardSettingsSS() {
  return fetchSS("/settings");
}

export async function fetchEnterpriseSettingsSS() {
  return fetchSS("/enterprise-settings");
}

export async function fetchCustomAnalyticsScriptSS() {
  return fetchSS("/enterprise-settings/custom-analytics-script");
}

export async function fetchSettingsSS(): Promise<CombinedSettings | null> {
  const tasks = [fetchStandardSettingsSS()];
  if (SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED) {
    tasks.push(fetchEnterpriseSettingsSS());
    if (CUSTOM_ANALYTICS_ENABLED) {
      tasks.push(fetchCustomAnalyticsScriptSS());
    }
  }

  try {
    const results = await Promise.all(tasks);

    let settings: Settings;
    if (!results[0].ok) {
      if (results[0].status === 403 || results[0].status === 401) {
        settings = {
          auto_scroll: true,
          product_gating: GatingType.NONE,
          gpu_enabled: false,
          maximum_chat_retention_days: null,
          notifications: [],
          needs_reindexing: false,
          anonymous_user_enabled: false,
        };
      } else {
        throw new Error(
          `fetchStandardSettingsSS failed: status=${
            results[0].status
          } body=${await results[0].text()}`
        );
      }
    } else {
      settings = await results[0].json();
    }

    let enterpriseSettings: EnterpriseSettings | null = null;
    if (tasks.length > 1) {
      if (!results[1].ok) {
        if (results[1].status !== 403 && results[1].status !== 401) {
          throw new Error(
            `fetchEnterpriseSettingsSS failed: status=${
              results[1].status
            } body=${await results[1].text()}`
          );
        }
      } else {
        enterpriseSettings = await results[1].json();
      }
    }

    let customAnalyticsScript: string | null = null;
    if (tasks.length > 2) {
      if (!results[2].ok) {
        if (results[2].status !== 403) {
          throw new Error(
            `fetchCustomAnalyticsScriptSS failed: status=${
              results[2].status
            } body=${await results[2].text()}`
          );
        }
      } else {
        customAnalyticsScript = await results[2].json();
      }
    }

    const webVersion = getWebVersion();

    const combinedSettings: CombinedSettings = {
      settings,
      enterpriseSettings,
      customAnalyticsScript,
      webVersion,
      webDomain: HOST_URL,
    };

    return combinedSettings;
  } catch (error) {
    console.error("fetchSettingsSS exception: ", error);
    return null;
  }
}

import {
  CombinedSettings,
  EnterpriseSettings,
  ApplicationStatus,
  Settings,
  QueryHistoryType,
} from "@/app/admin/settings/interfaces";
import {
  CUSTOM_ANALYTICS_ENABLED,
  HOST_URL,
  SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED,
} from "@/lib/constants";
import { fetchSS } from "@/lib/utilsSS";
import { getWebVersion } from "@/lib/version";

export enum SettingsError {
  OTHER = "OTHER",
}

export async function fetchStandardSettingsSS() {
  return fetchSS("/settings");
}

export async function fetchEnterpriseSettingsSS() {
  return fetchSS("/enterprise-settings");
}

export async function fetchCustomAnalyticsScriptSS() {
  return fetchSS("/enterprise-settings/custom-analytics-script");
}

export async function fetchSettingsSS(): Promise<CombinedSettings | null> {
  const tasks = [fetchStandardSettingsSS()];
  if (SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED) {
    tasks.push(fetchEnterpriseSettingsSS());
    if (CUSTOM_ANALYTICS_ENABLED) {
      tasks.push(fetchCustomAnalyticsScriptSS());
    }
  }

  try {
    const results = await Promise.all(tasks);

    let settings: Settings;

    const result_0 = results[0];
    if (!result_0) {
      throw new Error("Standard settings fetch failed.");
    }

    if (!result_0.ok) {
      if (result_0.status === 403 || result_0.status === 401) {
        settings = {
          auto_scroll: true,
          application_status: ApplicationStatus.ACTIVE,
          gpu_enabled: false,
          maximum_chat_retention_days: null,
          notifications: [],
          needs_reindexing: false,
          anonymous_user_enabled: false,
          deep_research_enabled: false,
          temperature_override_enabled: true,
          query_history_type: QueryHistoryType.NORMAL,
        };
      } else {
        throw new Error(
          `fetchStandardSettingsSS failed: status=${
            result_0.status
          } body=${await result_0.text()}`
        );
      }
    } else {
      settings = await result_0.json();
    }

    let enterpriseSettings: EnterpriseSettings | null = null;
    if (tasks.length > 1) {
      const result_1 = results[1];
      if (!result_1) {
        throw new Error("fetchEnterpriseSettingsSS failed.");
      }

      if (!result_1.ok) {
        if (result_1.status !== 403 && result_1.status !== 401) {
          throw new Error(
            `fetchEnterpriseSettingsSS failed: status=${
              result_1.status
            } body=${await result_1.text()}`
          );
        }
      } else {
        enterpriseSettings = await result_1.json();
      }
    }

    let customAnalyticsScript: string | null = null;
    if (tasks.length > 2) {
      const result_2 = results[2];
      if (!result_2) {
        throw new Error("fetchCustomAnalyticsScriptSS failed.");
      }

      if (!result_2.ok) {
        if (result_2.status !== 403) {
          throw new Error(
            `fetchCustomAnalyticsScriptSS failed: status=${
              result_2.status
            } body=${await result_2.text()}`
          );
        }
      } else {
        customAnalyticsScript = await result_2.json();
      }
    }

    if (settings.deep_research_enabled == null) {
      settings.deep_research_enabled = false;
    }

    const webVersion = getWebVersion();

    const combinedSettings: CombinedSettings = {
      settings,
      enterpriseSettings,
      customAnalyticsScript,
      webVersion,
      webDomain: HOST_URL,
    };

    return combinedSettings;
  } catch (error) {
    console.error("fetchSettingsSS exception: ", error);
    return null;
  }
}
