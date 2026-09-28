export type CallerIdStatus = 'pending' | 'verified' | 'failed';

export type CallerId = {
  phoneNumber: string;
  status: CallerIdStatus;
  label: string | null;
  isDefault: boolean;
  verifiedAt: string | null;
  source?: 'user' | 'twilio';
  callBlocked?: boolean;
  notice?: string | null;
};

export type CallingProvider = 'twilio' | 'telnyx';

export type CallingConfig = {
  enabled: boolean;
  canUseDialer?: boolean;
  provider?: CallingProvider;
  callerIds: CallerId[];
  hubspotLogging: boolean;
  settingsUrl?: string;
};

export type AddCallerIdResponse = {
  phoneNumber: string;
  status: CallerIdStatus;
  verificationCode?: string | null;
  alreadyVerified?: boolean;
  validationSid?: string;
  needsCodeSubmit?: boolean;
};
