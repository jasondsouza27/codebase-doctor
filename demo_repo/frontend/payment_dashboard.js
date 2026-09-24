import { formatCurrency } from './utils';

export class PaymentDashboard {
    constructor(apiEndpoint) {
        this.apiEndpoint = apiEndpoint || '/api/v1/payments';
        this.transactions = [];
    }

    async fetchTransactions(userId) {
        try {
            const response = await fetch(`${this.apiEndpoint}/user/${userId}`);
            if (!response.ok) {
                throw new Error(`Failed to fetch: ${response.statusText}`);
            }
            this.transactions = await response.json();
            return this.transactions;
        } catch (error) {
            console.error('Error fetching transactions:', error);
            throw error;
        }
    }

    async initiateRefund(transactionId, refundAmount) {
        if (refundAmount <= 0) {
            throw new Error('Refund amount must be positive');
        }
        const payload = { transactionId, amount: refundAmount };
        const response = await fetch(`${this.apiEndpoint}/refund`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return await response.json();
    }
}
