# Business Operations TODO

## 1. VAT billing and payment tracking

- [ ] Extend the existing VAT billing process to record how each customer bill is paid:
  - Cash.
  - Cheque, with the associated bank.
  - Mobile banking, supporting multiple banks/accounts.
  - Credit, with a bank name where applicable.
- [ ] Maintain bank/account records for cheque, mobile banking, and bank-related transactions.
- [ ] Track bill amounts, payments received, and outstanding balances.
- [ ] Record later deposits of collected cash into a bank account, including date, amount, and bank.
- [ ] Link cash deposits to the original cash collection where possible and avoid counting deposits as new income.
- [ ] Keep a transaction history for bill payments and cash-to-bank transfers.

## 2. Two-stage billing

- [ ] Stage 1: retain the current billing process for entering individual foam items and quantities.
- [ ] Stage 2: group foams with the same density and calculate their combined quantity.
- [ ] Allow the user to enter the rate for each density group during Stage 2.
- [ ] Calculate group totals and the final VAT bill from the grouped quantities and rates.
- [ ] Preserve the original item details alongside the grouped billing summary.
- [ ] Allow review and correction before finalizing the bill.

## 3. Purchase tracking

- [ ] Create purchase records with:
  - Bill number.
  - Supplier.
  - Billed date.
  - Received date.
  - Item details, quantities, and costs.
  - Payment method: credit, cash, or cheque.
  - Bank details for cheque payments.
- [ ] Track purchase payments and outstanding supplier balances.
- [ ] Distinguish recording a purchase bill from receiving its items.

## 4. Purchase receipt and item-wise inventory

- [ ] Add a receipt stage that can be created from a purchase record.
- [ ] Record actual received quantities and the receipt date for each item.
- [ ] Support partial receipts and show quantities still pending.
- [ ] Add received items to stock inventory item by item.
- [ ] Link inventory receipts to the originating purchase and purchase bill.
- [ ] Maintain stock movement records and current balances for each item.

## 5. Factory job orders and production inventory

- [ ] Maintain inventory item records for production materials and finished products.
- [ ] Create factory job orders with planned production details and required materials.
- [ ] Record materials issued from inventory against each job order.
- [ ] File a production job report against the job order.
- [ ] Record actual material consumption, finished quantities, and waste or losses.
- [ ] Receive factory-produced items into inventory before they are sold.
- [ ] Link finished stock to the job order and production report.
- [ ] Deduct sold items from finished-product inventory and link the movement to the customer bill.
- [ ] Track job status: planned, in progress, and completed.

## 6. Cash expenses

- [ ] Record cash expenses with date, category, amount, description, and supporting reference where available.
- [ ] Support categories such as labour, food, hotel, and other operating expenses.
- [ ] Allow expenses to have an optional third-party/payee reference.
- [ ] Allow expenses to be recorded without third-party information.
- [ ] Link an expense to a job order or worksheet when applicable.
- [ ] Include cash expenses in the cash balance and transaction history.

## 7. Worksheets, labour records, and salary calculation

- [ ] Create worksheets to record daily operations, completed work, and related job orders.
- [ ] Maintain worker records and applicable salary or labour rates.
- [ ] Record attendance, working time, overtime, or completed work quantities as required.
- [ ] Link labour entries to worksheets and factory job orders where applicable.
- [ ] Calculate salary using the agreed salary basis and recorded labour data.
- [ ] Track salary advances, deductions, payments, and unpaid balances.
- [ ] Produce worker-wise salary summaries for each pay period.
- [ ] Prevent salary payments and labour expense entries from counting the same cost twice.

## 8. Reports and reconciliation

- [ ] Customer bills, payments, and outstanding credit report.
- [ ] Cash balance, bank balances, and cash deposit report.
- [ ] Purchase, supplier balance, and pending receipt report.
- [ ] Item-wise stock balance and stock movement report.
- [ ] Job order, production output, material consumption, and waste report.
- [ ] Expense report by category, date, third party, and job order.
- [ ] Worksheet, labour, and salary report by worker and pay period.

## Details to confirm before implementation

- [ ] Clarify whether customer credit means an unpaid customer balance, bank-financed credit, or both, and when a bank name is required.
- [ ] Define the quantity unit and conversion rules used when grouping foam by density.
- [ ] Confirm VAT calculation, rounding, and rate rules for grouped bills.
- [ ] Confirm whether a single bill can use multiple payment methods or partial payments.
- [ ] Define when cheque payments affect cash/bank balances and how clearance is recorded.
- [ ] Define inventory item units, foam density attributes, and production conversion rules.
- [ ] Define salary bases, overtime rules, pay periods, advances, and deductions.

## Suggested implementation order

1. Item, bank/account, supplier, customer, and worker records.
2. Two-stage VAT billing and customer payment tracking.
3. Purchase tracking and item-wise inventory receipts.
4. Factory job orders, production reports, and finished-stock receipts.
5. Cash expenses and cash-to-bank transfers.
6. Worksheets, labour records, and salary calculation.
7. Reports and reconciliation across all modules.
