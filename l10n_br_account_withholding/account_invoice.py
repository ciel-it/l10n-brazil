# -*- encoding: utf-8 -*-
# #############################################################################
#
# Copyright (C) 2014 KMEE (http://www.kmee.com.br)
# @author Luis Felipe Mileo <mileo@kmee.com.br>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time

from openerp import api, fields, models
from openerp.addons import decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    issqn_wh = fields.Boolean(u'Retém ISSQN')
    issqn_value_wh = fields.Float(u'Valor da retenção do ISSQN',
                                  digits_compute=dp.get_precision('Account'))
    pis_wh = fields.Boolean(u'Retém PIS')
    pis_value_wh = fields.Float(u'Valor da retenção do PIS',
                                digits_compute=dp.get_precision('Account'))
    cofins_wh = fields.Boolean(u'Retém COFINS')
    cofins_value_wh = fields.Float(u'Valor da retenção do Cofins',
                                   digits_compute=dp.get_precision('Account'))
    csll_wh = fields.Boolean(u'Retém CSLL')
    csll_value_wh = fields.Float(u'Valor da retenção de CSLL',
                                 digits_compute=dp.get_precision('Account'))
    irrf_wh = fields.Boolean(u'Retém IRRF')
    irrf_base_wh = fields.Float(u'Base de calculo retenção do IRRF',
                                digits_compute=dp.get_precision('Account'))
    irrf_value_wh = fields.Float(u'Valor da retenção de IRRF',
                                 digits_compute=dp.get_precision('Account'))
    inss_wh = fields.Boolean(u'Retém INSS')
    inss_base_wh = fields.Float(
        u'Base de Cálculo da Retenção da Previdência Social',
        digits_compute=dp.get_precision('Account'))
    inss_value_wh = fields.Float(u'Valor da Retenção da Previdência Social ',
                                 digits_compute=dp.get_precision('Account'))

    def _whitholding_map(self, cr, uid, result, context=None, **kwargs):
        # TODO: Implementar o mapeamento cliente x empresa.

        if not context:
            context = {}

        obj_partner = self.pool.get('res.partner').browse(
            cr, uid, kwargs.get('partner_id', False))
        obj_company = self.pool.get('res.company').browse(
            cr, uid, kwargs.get('company_id', False))

        result['value'][
            'issqn_wh'] = obj_company.issqn_wh and obj_partner.partner_fiscal_type_id.issqn_wh
        result['value'][
            'inss_wh'] = obj_company.inss_wh and obj_partner.partner_fiscal_type_id.inss_wh
        result['value'][
            'pis_wh'] = obj_company.pis_wh and obj_partner.partner_fiscal_type_id.pis_wh
        result['value'][
            'cofins_wh'] = obj_company.cofins_wh and obj_partner.partner_fiscal_type_id.cofins_wh
        result['value'][
            'csll_wh'] = obj_company.csll_wh and obj_partner.partner_fiscal_type_id.csll_wh
        result['value'][
            'irrf_wh'] = obj_company.irrf_wh and obj_partner.partner_fiscal_type_id.irrf_wh

        return result

    def onchange_partner_id(self, cr, uid, ids, type, partner_id,
                            date_invoice=False, payment_term=False,
                            partner_bank_id=False, company_id=False,
                            fiscal_category_id=False):

        result = super(AccountInvoice, self).onchange_partner_id(
            cr, uid, ids, type, partner_id, date_invoice, payment_term,
            partner_bank_id, company_id, fiscal_category_id)

        return self._whitholding_map(
            cr, uid, result, False, partner_id=partner_id,
            partner_invoice_id=partner_id, company_id=company_id,
            fiscal_category_id=fiscal_category_id)

    def finalize_invoice_move_lines(self, cr, uid, invoice_browse, move_lines):
        move_lines = super(
            AccountInvoice,
            self).finalize_invoice_move_lines(
            cr,
            uid,
            invoice_browse,
            move_lines)

        # veriricar se o cliente x empresa retem o imposto e chamar o metodo
        # correspondente
     
        self._compute_wh(cr, uid, invoice_browse)
        return move_lines

    def _compute_wh(self, cr, uid, invoice_browse):
        period_obj = self.pool.get('account.period')
        line_obj = self.pool.get('account.invoice.line')

        if invoice_browse.company_id.wh_type == '1':
            raise osv.except_osv('Regime de Caixa Não implementado')
        elif invoice_browse.company_id.wh_type == '2':

            date_invoice = invoice_browse.date_invoice
            if not date_invoice:
                date_invoice = time.strftime('%Y-%m-%d')
            period_select = """SELECT id from account_period p where '%s' BETWEEN p.date_start AND p.date_stop;""" % date_invoice
            cr.execute(period_select)
            period_result = cr.dictfetchall()

            inv_state = ['paid', 'open']  # Incluir o estado = sefaz_export?
            inv_type = ['out_invoice']  # TODO: Tratar compras e devoluções
            invoice_ids = self.search(cr, uid, [('partner_id', '=', invoice_browse.partner_id.id),
                                                ('period_id',
                                                 '=',
                                                 period_result[0]['id']),
                                                ('state', 'in', inv_state),
                                                ('type', 'in', inv_type),
                                                ])
            result = {
                'pis_value_wh': 0.00,
                'cofins_value_wh': 0.00,
                'csll_value_wh': 0.00,
                'irrf_value_wh': 0.00,
                'issqn_value_wh': 0.00,
            }
            witholded = {
                'pis_value_wh': 0.00,
                'cofins_value_wh': 0.00,
                'csll_value_wh': 0.00,
                'irrf_value_wh': 0.00,
                'issqn_value_wh': 0.00,
                'irrf_base_wh': 0.00,
            }
            invoice = {
                'pis': 0.00,
                'cofins': 0.00,
                'csll': 0.00,
                'ir': 0.00,
            }
            previous = {
                'pis': 0.00,
                'cofins': 0.00,
                'csll': 0.00,
                'ir': 0.00,
            }
            amount_previous = 0.00

            for inv in self.browse(cr, uid, invoice_ids):
                amount_previous += inv.amount_services
                witholded['pis_value_wh'] += inv.pis_value_wh
                witholded['cofins_value_wh'] += inv.cofins_value_wh
                witholded['csll_value_wh'] += inv.csll_value_wh
                witholded['irrf_value_wh'] += inv.irrf_value_wh
                witholded['irrf_base_wh'] += inv.irrf_base_wh

                for line in inv.invoice_line:
                    if not line.product_type == 'service':
                        continue
                    previous['pis'] += line.pis_value
                    previous['cofins'] += line.cofins_value
                    previous['csll'] += line.csll_value
                    previous['ir'] += line.ir_value

            for current_line in invoice_browse.invoice_line:
                if current_line.product_type == 'service':
                    invoice['pis'] += current_line.pis_value
                    invoice['cofins'] += current_line.cofins_value
                    invoice['csll'] += current_line.csll_value
                    invoice['ir'] += current_line.ir_value
                    # ISSQN
                    # TODO invoice_browse.issqn_wh ERROOOOOOO !!! só entra
                    # quando
                    if current_line.issqn_cst_id.code in (
                            'R') and invoice_browse.issqn_wh:
                        result['issqn_value_wh'] += current_line.issqn_value

           # PIS / COFINS / CSLL
            if (amount_previous +
                    invoice_browse.amount_services) > invoice_browse.company_id.cofins_csll_pis_wh_base:
                if invoice_browse.pis_wh:
                    result['pis_value_wh'] = invoice['pis'] + \
                        previous['pis'] - witholded['pis_value_wh']
                if invoice_browse.cofins_wh:
                    result['cofins_value_wh'] = invoice['cofins'] + \
                        previous['cofins'] - witholded['cofins_value_wh']
                if invoice_browse.csll_wh:
                    result['csll_value_wh'] = invoice['csll'] + \
                        previous['csll'] - witholded['csll_value_wh']

            # IR: Existem divergencias entre as normativas verificar melhor a legislação
            # Pode ser que o total deva acumular para os proximos meses.
            if invoice_browse.irrf_wh:
                irrf_base = amount_previous + \
                    invoice_browse.amount_services - witholded['irrf_base_wh']
                irrf_value_wh = irrf_base * \
                    invoice_browse.partner_id.partner_fiscal_type_id.irrf_wh_percent / \
                    100
                if irrf_value_wh > invoice_browse.company_id.irrf_wh_base:
                    result['irrf_value_wh'] = irrf_value_wh
                    result['irrf_base_wh'] = irrf_base

            # INSS
            if invoice_browse.inss_wh:
                pass
                # TODO

            self.write(cr, uid, [invoice_browse.id], result)

    # def compute_invoice_totals(self, cr, uid, inv, company_currency, ref, invoice_move_lines, context=None):
    #     total, total_currency, invoice_move_lines = super(AccountInvoice, self).compute_invoice_totals(cr, uid, inv,
    #                                                                                                    company_currency,
    #                                                                                                    ref,
    #                                                                                                    invoice_move_lines,
    #                                                                                                    context=None)
    #     return total, total_currency, invoice_move_lines


# class AccountInvoiceLine(orm.Model):
#     _inherit = 'account.invoice.line'
#
#     # _columns = {
#     # TODO: Implmentar o calculo de retenção de ISS que varia por item.
#     # }
#
#     def fields_view_get(self, cr, uid, view_id=None, view_type=False,
#                         context=None, toolbar=False, submenu=False):
#         result = super(AccountInvoiceLine, self).fields_view_get(
#             cr, uid, view_id=view_id, view_type=view_type, context=context,
#             toolbar=toolbar, submenu=submenu)
#
#         return result
#
#     def product_id_change(self, cr, uid, ids, product, uom, qty=0, name='',
#                           type='out_invoice', partner_id=False,
#                           fposition_id=False, price_unit=False,
#                           currency_id=False, context=None, company_id=False,
#                           parent_fiscal_category_id=False,
#                           parent_fposition_id=False):
#         result = super(AccountInvoiceLine, self).product_id_change(
#             cr, uid, ids, product, uom, qty, name, type, partner_id,
#             fposition_id, price_unit, currency_id, context, company_id,
#             parent_fiscal_category_id, parent_fposition_id)
#
#         return result
#
#
# class AccountInvoiceTax(orm.Model):
#     _inherit = 'account.invoice.tax'
#
#     def move_line_get(self, cr, uid, invoice_id):
#         res = super(AccountInvoiceTax, self).move_line_get(cr, uid, invoice_id)
#         return res

