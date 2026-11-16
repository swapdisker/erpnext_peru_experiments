// Copyright (c) 2026, erpnext_peru contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.country !== "Peru") {
			return;
		}
		if (!frappe.user.has_role("System Manager") && !frappe.user.has_role("Accounts Manager")) {
			return;
		}
		frm.add_custom_button(__("Apply PCGE 2019"), () => erpnext_peru.apply_pcge(frm), __("Peru"));
		frm.add_custom_button(__("Set Up IGV"), () => erpnext_peru.setup_igv(frm), __("Peru"));
	},
});

frappe.provide("erpnext_peru");

erpnext_peru.list_html = function (rows, render) {
	const shown = rows.slice(0, 15).map((row) => `<li>${render(row)}</li>`);
	if (rows.length > 15) {
		shown.push(`<li>${__("and {0} more", [rows.length - 15])}</li>`);
	}
	return `<ul>${shown.join("")}</ul>`;
};

erpnext_peru.pcge_report_html = function (report) {
	const esc = frappe.utils.escape_html;
	let html = "<p>";
	html += report.dry_run
		? __("{0} accounts would be created.", [report.created.length])
		: __("{0} accounts were created.", [report.created.length]);
	html += " " + __("{0} already existed.", [report.existing]) + "</p>";
	if (report.replaced_existing && report.dry_run) {
		html += `<p class="text-danger">${__(
			"The current chart of accounts of the company would be deleted first."
		)}</p>`;
	}
	if (report.name_differences.length) {
		html += `<p>${__("Accounts whose name differs from the PCGE (the company's name is kept):")}</p>`;
		html += erpnext_peru.list_html(
			report.name_differences,
			(row) => `${esc(row.code)}: ${esc(row.company_name)} / ${esc(row.pcge_name)}`
		);
	}
	if (report.conflicts.length) {
		html += `<p class="text-danger">${__("Conflicts that need a decision (nothing was overwritten):")}</p>`;
		html += erpnext_peru.list_html(report.conflicts, (row) => `${esc(row.code)}: ${esc(row.detail)}`);
	}
	if (report.skipped.length) {
		html += `<p>${__("{0} accounts were not created because of those conflicts.", [
			report.skipped.length,
		])}</p>`;
	}
	if (report.defaults_provisional && report.defaults_provisional.length) {
		html += `<p>${__("Company defaults set provisionally, to be confirmed by the accountant:")} ${esc(
			report.defaults_provisional.join(", ")
		)}</p>`;
	}
	if (report.defaults_left_empty && report.defaults_left_empty.length) {
		html += `<p>${__("Company defaults left for the accountant to choose:")} ${esc(
			report.defaults_left_empty.join(", ")
		)}</p>`;
	}
	return html;
};

erpnext_peru.apply_pcge = function (frm) {
	frappe.prompt(
		[
			{
				fieldname: "replace_existing",
				fieldtype: "Check",
				label: __("Delete the current chart of accounts first"),
				description: __(
					"Only possible while the company has no ledger entries. Leave it unticked to add the missing PCGE accounts and keep everything else."
				),
			},
		],
		(values) => {
			const args = { company: frm.doc.name, replace_existing: values.replace_existing ? 1 : 0 };
			frappe.call({
				method: "erpnext_peru.accounts.api.preview_pcge",
				args: args,
				freeze: true,
				callback(response) {
					if (!response.message) {
						return;
					}
					frappe.confirm(erpnext_peru.pcge_report_html(response.message), () => {
						frappe.call({
							method: "erpnext_peru.accounts.api.apply_pcge_to_company",
							args: args,
							freeze: true,
							callback(result) {
								if (result.message) {
									erpnext_peru.wait_for_pcge(frm);
								}
							},
						});
					});
				},
			});
		},
		__("Apply PCGE 2019"),
		__("Preview")
	);
};

// The accounts are created by a background job: ask for its state until it ends.
erpnext_peru.wait_for_pcge = function (frm) {
	const interval = 3000;
	const give_up_after = 20 * 60 * 1000;
	const started = Date.now();
	frappe.dom.freeze(
		__("Creating the accounts in the background. This can take a few minutes; keep this page open.")
	);
	const finish = (options) => {
		frappe.dom.unfreeze();
		frappe.msgprint(options);
	};
	const check = () => {
		frappe.call({
			method: "erpnext_peru.accounts.api.pcge_job_status",
			args: { company: frm.doc.name },
			callback(response) {
				const state = response.message || {};
				if (state.status === "done") {
					finish({
						title: __("PCGE applied"),
						indicator: state.report.conflicts.length ? "orange" : "green",
						message: erpnext_peru.pcge_report_html(state.report),
					});
					frm.reload_doc();
				} else if (state.status === "failed") {
					finish({
						title: __("The PCGE could not be applied"),
						indicator: "red",
						message:
							frappe.utils.escape_html(state.error || "") +
							`<p>${__("Nothing was changed.")}</p>`,
					});
				} else if (Date.now() - started > give_up_after) {
					finish({
						title: __("Still working"),
						indicator: "orange",
						message: __(
							"It is taking longer than expected. The job continues in the background: reload this page in a few minutes and check the chart of accounts."
						),
					});
				} else {
					setTimeout(check, interval);
				}
			},
			error() {
				finish({
					title: __("Still working"),
					indicator: "orange",
					message: __(
						"It is taking longer than expected. The job continues in the background: reload this page in a few minutes and check the chart of accounts."
					),
				});
			},
		});
	};
	setTimeout(check, interval);
};

erpnext_peru.setup_igv = function (frm) {
	frappe.confirm(
		__(
			"Create the IGV tax categories, the sales and purchase tax templates (18% and 0%) and their tax rules for this company?"
		),
		() => {
			frappe.call({
				method: "erpnext_peru.accounts.api.setup_igv_for_company",
				args: { company: frm.doc.name },
				freeze: true,
				callback(response) {
					const report = response.message;
					if (!report) {
						return;
					}
					const esc = frappe.utils.escape_html;
					let html = `<p>${__("{0} records created, {1} already existed.", [
						report.created.length,
						report.existing.length,
					])}</p>`;
					if (report.disabled.length) {
						html += `<p>${__("Disabled (ERPNext's 16% default):")}</p>`;
						html += erpnext_peru.list_html(report.disabled, (row) => esc(row));
					}
					if (report.default_changed.length) {
						html += `<p>${__("Default template changed:")}</p>`;
						html += erpnext_peru.list_html(report.default_changed, (row) => esc(row));
					}
					(report.warnings || []).forEach((warning) => {
						html += `<p class="text-warning">${warning}</p>`;
					});
					frappe.msgprint({
						title: __("IGV set up"),
						indicator: (report.warnings || []).length ? "orange" : "green",
						message: html,
					});
				},
			});
		}
	);
};
