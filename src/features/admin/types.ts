export type AdminCrmConnection = {
  provider: string;
  status: string;
  tokenExpiresAt: string | null;
};

export type AdminAccountListItem = {
  id: string;
  email: string;
  fullName: string | null;
  companyName: string | null;
  phone: string | null;
  createdAt: string;
  lastSignInAt: string | null;
  crm: AdminCrmConnection[];
  memoCount: number;
  approvedCount: number;
  failedCount: number;
  lastMemoAt: string | null;
};

export type AdminAccountConfiguration = {
  defaultPipelineName: string | null;
  defaultStageName: string | null;
  allowedDealFields: string[];
  allowedContactFields: string[];
  allowedCompanyFields: string[];
  allowedLineItemFields: string[];
  autoCreateContacts: boolean | null;
  autoCreateCompanies: boolean | null;
  lostLeadStatusValue: string | null;
  onHoldLeadStatusValue: string | null;
};

export type AdminAccountConnection = {
  id: string;
  provider: string;
  status: string;
  tokenExpiresAt: string | null;
  lastSyncedAt: string | null;
  configuration: AdminAccountConfiguration | null;
};

export type AdminRecentMemo = {
  id: string;
  status: string;
  source: string | null;
  createdAt: string;
  company: string;
  errorMessage: string | null;
};

export type AdminUsageWeeklyDay = {
  day: string;
  memos: number;
};

export type AdminUsageActivity = {
  action: string;
  company: string;
  time: string;
  type: string;
};

export type AdminUsage = {
  totalMemos: number;
  approvedCount: number;
  thisWeekMemos: number;
  thisWeekApproved: number;
  timeSavedHours: number;
  thisWeekTimeSavedHours: number;
  accuracyPct: number | null;
  weekly: AdminUsageWeeklyDay[];
  recentActivity: AdminUsageActivity[];
};

export type AdminAccountDetail = {
  id: string;
  email: string;
  fullName: string | null;
  companyName: string | null;
  phone: string | null;
  createdAt: string;
  lastSignInAt: string | null;
  productContext: string;
  sttLanguages: string[];
  glossaryLength: number;
  primaryCrmConnectionId: string | null;
  connections: AdminAccountConnection[];
  recentMemos: AdminRecentMemo[];
  usage: AdminUsage;
};

export type AdminAccountListResponse = {
  accounts: AdminAccountListItem[];
  total: number;
  skip: number;
  limit: number;
};

export type AdminStuckMemo = {
  id: string;
  userId: string;
  status: string;
  processingStartedAt: string | null;
  errorMessage: string | null;
};

export type AdminRuntime = {
  sttProvider: string;
  llmProvider: string;
  extractionModel: string;
  copilotModel: string;
  environment: string;
};

export type AdminImpersonateResponse = {
  user: {
    id: string;
    email: string;
    fullName: string | null;
    companyName: string | null;
  };
  accessToken: string;
  refreshToken: string;
};
