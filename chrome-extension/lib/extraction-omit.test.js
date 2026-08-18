import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  canEditOrRemoveProposedField,
  proposedFieldKey,
  stripOmittedFields,
  applyProposedUpdates,
  buildApproveExtraction,
} from './extraction-omit.js';

describe('canEditOrRemoveProposedField', () => {
  it('allows bin on contact, deal, and company properties', () => {
    assert.equal(canEditOrRemoveProposedField({ object_type: 'contacts', field_name: 'phone' }), true);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'deals', field_name: 'amount' }), true);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'companies', field_name: 'domain' }), true);
  });

  it('does not treat identity labels or insights or line items as removable rows', () => {
    assert.equal(canEditOrRemoveProposedField({ object_type: 'contacts', field_name: 'contact_name' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'companies', field_name: 'company_name' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'deals', field_name: 'dealname' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'deals', field_name: 'description' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'deals', field_name: 'hs_next_step' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'line_items', field_name: 'name' }), false);
    assert.equal(canEditOrRemoveProposedField({ object_type: 'deals', field_name: 'line_item_0_name' }), false);
  });
});

describe('stripOmittedFields', () => {
  it('drops a contact property and its identity source so approve cannot write it', () => {
    const extraction = {
      contactPhone: '+34600111222',
      raw_extraction: { contact_properties: { phone: '+34600111222', jobtitle: 'CEO' } },
    };
    const next = stripOmittedFields(extraction, [proposedFieldKey({ object_type: 'contacts', field_name: 'phone' })]);
    assert.equal(next.contactPhone, null);
    assert.equal(next.raw_extraction.contact_properties.phone, undefined);
    assert.equal(next.raw_extraction.contact_properties.jobtitle, 'CEO');
  });

  it('drops a deal amount from both top-level extraction and raw aliases', () => {
    const extraction = {
      dealAmount: 9000,
      raw_extraction: { amount: 9000, Amount: 9000, closedate: '2026-09-01' },
    };
    const next = stripOmittedFields(extraction, ['deals:amount']);
    assert.equal(next.dealAmount, null);
    assert.equal(next.raw_extraction.amount, undefined);
    assert.equal(next.raw_extraction.Amount, undefined);
    assert.equal(next.raw_extraction.closedate, '2026-09-01');
  });

  it('drops a company domain from nested properties without inventing a new company', () => {
    const extraction = {
      companyName: 'Acme',
      raw_extraction: { company_properties: { name: 'Acme', domain: 'acme.test' } },
    };
    const next = stripOmittedFields(extraction, ['companies:domain']);
    assert.equal(next.companyName, 'Acme');
    assert.equal(next.raw_extraction.company_properties.domain, undefined);
    assert.equal(next.raw_extraction.company_properties.name, 'Acme');
  });
});

describe('buildApproveExtraction', () => {
  it('keeps remaining edits and omits binned fields instead of leaving stored extraction values', () => {
    const memoExtraction = {
      contactPhone: '+34000000000',
      dealAmount: 5000,
      summary: 'Old summary',
      raw_extraction: {
        amount: 5000,
        contact_properties: { phone: '+34000000000', jobtitle: 'VP' },
      },
    };
    const next = buildApproveExtraction({
      memoExtraction,
      updates: [
        { object_type: 'contacts', field_name: 'jobtitle', new_value: 'CRO' },
      ],
      omittedKeys: ['contacts:phone', 'deals:amount'],
      summary: 'Call recap',
      nextSteps: ['Send proposal'],
    });
    assert.equal(next.raw_extraction.contact_properties.jobtitle, 'CRO');
    assert.equal(next.raw_extraction.contact_properties.phone, undefined);
    assert.equal(next.contactPhone, null);
    assert.equal(next.dealAmount, null);
    assert.equal(next.raw_extraction.amount, undefined);
    assert.equal(next.summary, 'Call recap');
    assert.deepEqual(next.nextSteps, ['Send proposal']);
    assert.equal(next.raw_extraction.hs_next_step, 'Send proposal');
  });
});

describe('applyProposedUpdates', () => {
  it('writes contact and company values into nested property bags', () => {
    const next = applyProposedUpdates(
      { raw_extraction: {} },
      [
        { object_type: 'contacts', field_name: 'phone', new_value: '555' },
        { object_type: 'companies', field_name: 'domain', new_value: 'acme.test' },
        { object_type: 'deals', field_name: 'amount', new_value: '12' },
      ]
    );
    assert.equal(next.raw_extraction.contact_properties.phone, '555');
    assert.equal(next.raw_extraction.company_properties.domain, 'acme.test');
    assert.equal(next.dealAmount, 12);
    assert.equal(next.raw_extraction.amount, 12);
  });
});
