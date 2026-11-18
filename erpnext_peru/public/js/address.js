// Copyright (c) 2026, erpnext_peru contributors
// License: GNU General Public License v3. See license.txt

// Choosing a Ubigeo fills City, County and State when they are empty. The server
// does the same on save (overrides/address.py), but City is mandatory in the
// form, so without this the user would have to type it first.
frappe.ui.form.on("Address", {
	async pe_ubigeo(frm) {
		const code = frm.doc.pe_ubigeo;
		if (!code) return;
		const { message } = await frappe.db.get_value("Ubigeo", code, ["district", "province", "department"]);
		if (!message || frm.doc.pe_ubigeo !== code) return; // changed again meanwhile
		const fill = { city: message.district, county: message.province, state: message.department };
		for (const [fieldname, value] of Object.entries(fill)) {
			if (!frm.doc[fieldname] && value) {
				await frm.set_value(fieldname, value);
			}
		}
	},
});
