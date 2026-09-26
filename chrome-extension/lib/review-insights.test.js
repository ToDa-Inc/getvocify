import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  visibleCrmUpdates,
  formatTaskDueLabel,
  shouldCreateHubSpotNote,
  taskRowsFromPreview,
  TRANSCRIPT_DETAILS_OPEN_DEFAULT,
  crmFieldDisplayLabel,
  crmFieldValueLabel,
  crmFieldWasLabel,
  crmFieldInputKind,
  crmFieldGroups,
  addFieldOptionLabel,
  shouldShowCrmFieldsSection,
  crmFieldTone,
  withLeadStatusOption,
} from './review-insights.js';

describe('visibleCrmUpdates', () => {
  it('hides email/phone and leaves a real job title change', () => {
    const out = visibleCrmUpdates([
      { object_type: 'contacts', field_name: 'email', new_value: 'a@b.com', current_value: 'a@b.com' },
      { object_type: 'contacts', field_name: 'phone', new_value: '+34', current_value: '+34' },
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired', current_value: 'Sales Director' },
      { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Follow up' },
    ]);
    assert.equal(out.length, 1);
    assert.equal(out[0].field_name, 'jobtitle');
  });

  it('keeps already-applied fields after HubSpot write', () => {
    const out = visibleCrmUpdates([
      {
        object_type: 'contacts',
        field_name: 'hs_lead_status',
        new_value: 'OPEN',
        current_value: 'OPEN',
        already_applied: true,
      },
      {
        object_type: 'contacts',
        field_name: 'hubspot_owner_id',
        new_value: '99',
        current_value: '99',
        already_applied: true,
      },
    ]);
    assert.equal(out.length, 2);
    assert.deepEqual(out.map((u) => u.field_name), ['hs_lead_status', 'hubspot_owner_id']);
  });

  it('still hides an unchanged field that this memo did not write', () => {
    const out = visibleCrmUpdates([
      {
        object_type: 'contacts',
        field_name: 'jobtitle',
        new_value: 'Retired',
        current_value: 'Retired',
      },
    ]);
    assert.equal(out.length, 0);
  });

  it('keeps the deal stage row even when the suggested stage is the current one', () => {
    const out = visibleCrmUpdates([
      { object_type: 'deals', field_name: 'dealstage', new_value: 'qualifiedtobuy', current_value: 'qualifiedtobuy' },
      { object_type: 'deals', field_name: 'stage_id', new_value: '11', current_value: '11' },
    ]);
    assert.equal(out.length, 2);
  });

  it('always keeps lead status, and pins a blank row when the model did not propose one', () => {
    const unchanged = visibleCrmUpdates([
      {
        object_type: 'contacts',
        field_name: 'hs_lead_status',
        new_value: 'OPEN',
        current_value: 'OPEN',
      },
    ]);
    assert.equal(unchanged.length, 1);

    const pinned = withLeadStatusOption([], [{
      name: 'hs_lead_status',
      label: 'Lead status',
      object_type: 'contacts',
      type: 'enumeration',
      current_value: 'NEW',
      options: [
        { value: 'NEW', label: 'New' },
        { value: 'ATTEMPTED_TO_CONTACT', label: 'Attempted to Contact' },
        { value: 'UNQUALIFIED', label: 'Unqualified' },
      ],
    }]);
    assert.equal(visibleCrmUpdates(pinned).length, 1);
    assert.equal(pinned[0].current_value, 'NEW');
    assert.equal(pinned[0].new_value, '');
    assert.equal(pinned[0].options.length, 3);

    const first = withLeadStatusOption(
      [{ object_type: 'contacts', field_name: 'jobtitle', new_value: 'Ops' }],
      [{
        name: 'hs_lead_status',
        label: 'Lead status',
        object_type: 'contacts',
        type: 'enumeration',
        current_value: 'NEW',
        options: [{ value: 'NEW', label: 'New' }, { value: 'CONNECTED', label: 'Connected' }],
      }],
    );
    assert.equal(first[0].field_name, 'jobtitle');
    assert.equal(first[1].field_name, 'hs_lead_status');
    assert.equal(crmFieldTone(first[1]), 'quiet');
    assert.equal(crmFieldValueLabel(first[1]), 'New');
    assert.equal(crmFieldWasLabel(first[1]), '');

    const withOptions = withLeadStatusOption(
      [{ object_type: 'contacts', field_name: 'hs_lead_status', new_value: 'CONNECTED', options: [] }],
      [{
        name: 'hs_lead_status',
        label: 'Lead status',
        object_type: 'contacts',
        options: [{ value: 'CONNECTED', label: 'Connected' }],
      }],
    );
    assert.equal(withOptions.length, 1);
    assert.equal(withOptions[0].new_value, 'CONNECTED');
    assert.equal(withOptions[0].options[0].value, 'CONNECTED');

    const again = withLeadStatusOption(pinned, [{
      name: 'hs_lead_status',
      label: 'Lead status',
      options: [{ value: 'NEW', label: 'New' }],
    }]);
    assert.equal(again.filter((u) => u.field_name === 'hs_lead_status').length, 1);
  });

  it('returns empty when the call only had a note and tasks', () => {
    assert.equal(visibleCrmUpdates([]).length, 0);
  });
});

describe('crm field rows', () => {
  it('uses the HubSpot field name only — no object stamp, no extra fetch', () => {
    assert.equal(
      crmFieldDisplayLabel({
        object_type: 'contacts',
        field_name: 'jobtitle',
        field_label: 'Job title',
      }),
      'Job title',
    );
    assert.equal(
      crmFieldDisplayLabel({ object_type: 'contacts', field_name: 'jobtitle' }),
      'jobtitle',
    );
  });

  it('shows the option label for enum values, not the internal id', () => {
    const update = {
      field_name: 'hs_lead_status',
      field_label: 'Lead status',
      new_value: 'UNQUALIFIED',
      current_value: 'NEW',
      options: [
        { value: 'NEW', label: 'New' },
        { value: 'UNQUALIFIED', label: 'Unqualified' },
      ],
    };
    assert.equal(crmFieldValueLabel(update), 'Unqualified');
    assert.equal(crmFieldWasLabel(update), 'New');
    assert.equal(crmFieldTone(update), 'status');
    assert.equal(crmFieldInputKind(update), 'select');
  });

  it('hides Was when HubSpot had nothing; uses date/text inputs from the field itself', () => {
    assert.equal(
      crmFieldWasLabel({ field_name: 'jobtitle', new_value: 'Retired', current_value: '(empty)' }),
      '',
    );
    assert.equal(
      crmFieldInputKind({ field_name: 'closedate', field_type: 'date', new_value: '2026-09-01' }),
      'date',
    );
    assert.equal(
      crmFieldInputKind({ field_name: 'jobtitle', field_type: 'string', new_value: 'Retired' }),
      'text',
    );
    assert.equal(
      crmFieldTone({ field_name: 'jobtitle', new_value: 'Retired', current_value: '(empty)' }),
      'new',
    );
    assert.equal(
      crmFieldTone({
        field_name: 'jobtitle',
        new_value: 'Retired',
        current_value: 'Sales Director',
      }),
      'override',
    );
    assert.equal(
      crmFieldTone({
        field_name: 'hs_lead_status',
        new_value: 'OPEN',
        current_value: 'OPEN',
        already_applied: true,
      }),
      'written',
    );
  });

  it('does not promote deal stage/amount — groups only when objects are mixed', () => {
    const contactOnly = crmFieldGroups([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired' },
      { object_type: 'contacts', field_name: 'lifecyclestage', field_label: 'Lifecycle stage', new_value: 'opportunity' },
    ]);
    assert.equal(contactOnly.length, 1);
    assert.equal(contactOnly[0].label, null);
    assert.deepEqual(contactOnly[0].updates.map((u) => u.field_name), ['jobtitle', 'lifecyclestage']);

    const mixed = crmFieldGroups([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: 'Retired' },
      { object_type: 'companies', field_name: 'industry', field_label: 'Industry', new_value: 'Chemicals' },
      { object_type: 'deals', field_name: 'amount', field_label: 'Amount', new_value: '12' },
    ]);
    assert.deepEqual(mixed.map((g) => g.label), ['Contact', 'Company', 'Deal']);
    assert.equal(mixed[2].updates[0].field_name, 'amount');
  });

  it('labels company fields as New company when review will create one', () => {
    const onlyCompany = crmFieldGroups(
      [{ object_type: 'companies', field_name: 'crm_utilizado', new_value: 'zoho' }],
      { creatingCompany: true },
    );
    assert.equal(onlyCompany[0].label, 'New company');

    const mixedCreate = crmFieldGroups(
      [
        { object_type: 'contacts', field_name: 'vocify_fit', new_value: 'moderate' },
        { object_type: 'companies', field_name: 'crm_utilizado', new_value: 'zoho' },
      ],
      { creatingCompany: true },
    );
    assert.deepEqual(mixedCreate.map((g) => g.label), ['Contact', 'New company']);
  });

  it('labels Add field with just the name unless objects are mixed', () => {
    const field = { name: 'jobtitle', label: 'Job title', object_type: 'contacts' };
    assert.equal(addFieldOptionLabel(field, { mixedObjects: false }), 'Job title');
    assert.equal(addFieldOptionLabel(field, { mixedObjects: true }), 'Contact · Job title');
  });

  it('keeps the Fields section when there is nothing proposed but fields can still be added', () => {
    assert.equal(shouldShowCrmFieldsSection({ updates: [], availableCount: 4 }), true);
    assert.equal(shouldShowCrmFieldsSection({ updates: [], availableCount: 0 }), false);
    assert.equal(
      shouldShowCrmFieldsSection({
        updates: [{ field_name: 'jobtitle', new_value: 'Retired' }],
        availableCount: 0,
      }),
      true,
    );
  });

  it('keeps a field the user just added so they can fill it', () => {
    const out = visibleCrmUpdates([
      { object_type: 'contacts', field_name: 'jobtitle', field_label: 'Job title', new_value: '', userAdded: true },
    ]);
    assert.equal(out.length, 1);
  });
});

describe('tasks and note', () => {
  it('pairs nextSteps with schedule ISO dates', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Follow up with ops', 'Send one-pager'],
      nextStepSchedules: ['2026-08-20', ''],
    });
    assert.equal(rows[0].dueDate, '2026-08-20');
    assert.equal(rows[1].dueDate, null);
    assert.equal(rows[0].checked, true);
  });

  it('uses the preview due date when the LLM schedule is a spoken phrase', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Contactar a Aritzel Expuru'],
      nextStepSchedules: ['martes 18:00'],
      proposedUpdates: [
        {
          object_type: 'task',
          field_name: 'next_step_task_0',
          new_value: 'Contactar a Aritzel Expuru',
          due_date: '2026-08-20',
        },
      ],
    });
    assert.equal(rows[0].dueDate, '2026-08-20');
    assert.equal(rows[0].text, 'Contactar a Aritzel Expuru');
  });

  it('does not invent a date when the LLM did not detect one', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Send one-pager'],
      nextStepSchedules: [''],
      proposedUpdates: [
        { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Send one-pager' },
      ],
    });
    assert.equal(rows[0].dueDate, null);
  });

  it('takes rows, count and dates from commitment rows, not from the legacy next steps', () => {
    const rows = taskRowsFromPreview({
      nextSteps: ['Mandar el caso'],
      nextStepSchedules: ['2026-09-25'],
      proposedUpdates: [
        { object_type: 'task', field_name: 'next_step_task_0', new_value: 'Enviar el caso', due_date: '2026-09-24', commitment_id: 'com-2' },
        { object_type: 'task', field_name: 'next_step_task_1', new_value: 'Preparar la propuesta', due_date: null, commitment_id: 'com-3' },
      ],
    });
    assert.deepEqual(
      rows.map((r) => [r.text, r.dueDate]),
      [['Enviar el caso', '2026-09-24'], ['Preparar la propuesta', null]],
    );
  });

  it('formats a due date as a short weekday chip', () => {
    assert.equal(
      formatTaskDueLabel('2026-08-20', { today: '2026-08-18' }),
      'Thu 20',
    );
  });

  it('always creates a note when there is a summary', () => {
    assert.equal(shouldCreateHubSpotNote({ summary: 'Retired.', transcript: '' }), true);
    assert.equal(shouldCreateHubSpotNote({ summary: '', transcript: '' }), false);
  });

  it('keeps the transcript collapsed by default', () => {
    assert.equal(TRANSCRIPT_DETAILS_OPEN_DEFAULT, false);
  });
});
