# Stock Manager

**Stock Manager** is a local Python application for family stock management. The objective of this project is to record purchase date, expiration date, storage location, quantity, and send notifications and restocking-list reminders accordingly.

*Version 1* only provides a CLI interface.

## Core objective

- Record family stock
- Supports searching by user, category, location, and keyword.
- Supports different expiration periods for unopened and opened products.
- Supports food with no expiration date by saving the expiration period as infinite.
- Supports consumption, deletion, and restocking.
- Supports macOS system notifications.
- Supports email notifications, making it easy to receive alerts in your mobile email app.
- Supports sending shopping list on fixed weekly shopping days.

## Main Features

### 1. Adding stock

The application supports the recording of the following information:

- Name
- Category (e.g., vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Opened or unopened
- Opening date
- Expiration date after opening
- Storage location (e.g., refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)
- Notes

For products without an expiration date, the user should still enter an expiration value, but the value should be saved as infinite.

### 2. Stock Overview

The application must support viewing current available stock and display:

- Name
- Category
- Purchaser or assigned user
- Quantity and unit
- Storage location
- Current effective expiration date
- Status
- Note

Stock status includes:

- `active`
- `consumed`
- `expiring soon`
- `expired`

### 3. Consume and Delete

The application supports opening, partial consumption, and full consumption.

Rule:

* After opening, ask for the date of opening and the expiration date after opening.
* Decrease the stock quantity when a portion is consumed.
* Set the status to `consumed` when the quantity reaches zero.
* When an item is deleted, confirm the command and remove the item from the stock records.
* After an item is fully consumed or deleted, ask whether to add it to the restocking list.

### 4. Validation of Required Information

When adding or editing inventory, the following fields must be filled in:

* Opened or unopened

If opened: 

- Name
- Category (e.g., vegetable, meat, fruit, medicine, frozen food, pet food, etc.)
- Purchaser or assigned user
- Date of purchase
- Opening date
- Expiration date after opening
- Storage location (e.g., refrigerator, freezer, storage cabinet, etc.)
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)

If unopened:

- Name
- Category
- Purchaser or assigned user
- Date of purchase
- Expiration date when unopened
- Storage location
- Quantity
- Unit (e.g., pieces, blocks, grams, bags, bottles, etc.)

If a product has no expiration date, the expiration value should be entered as infinite.

If required information is missing, the CLI should immediately prompt the user to provide it, rather than saving incomplete data.

### 5. Search and Filter

The search scope includes:

- Name
- Category
- Purchaser or assigned user
- Storage location
- Note

Support filtering based on the following criteria:

- Category
- Purchaser or assigned user
- Storage location
- Expiring soon
- Expired

### 6. Restocking list and Weekly Shopping Day Reminder

In the following scenarios, ask whether to add the item to the restocking list:

- The food has expired
- The food has been consumed
- The food has been manually deleted

The application supports setting a fixed weekly shopping day.

When the reminder command is executed, if it is a shopping day, the application should check the restocking list and send a reminder. The application should not clear the restocking list automatically. Items should only be marked as done manually.

### 7. Expiration Reminder

By default, reminders for food nearing its expiration date are sent 2 days in advance.

Rule:

- For opened food items, the expiration date after opening applies.
- For unopened food items, the expiration date on the package applies.
- Items with an infinite expiration period are not included in expiration reminders.
- Deleted and consumed food items are not included in expiration reminders.

### 8. Notification Method

The first version supports two notification methods:

- macOS system notifications
- Email alerts

macOS notifications are enabled by default.

Email alerts are an optional feature. If no email address is configured, the application should not stop running; it should simply display a message in the CLI indicating that email alerts are not configured.
