# -*- encoding: utf-8 -*-
###############################################################################
#                                                                             #
# Copyright (C) 2013  Renato Lima - Akretion                                  #
#                                                                             #
#This program is free software: you can redistribute it and/or modify         #
#it under the terms of the GNU Affero General Public License as published by  #
#the Free Software Foundation, either version 3 of the License, or            #
#(at your option) any later version.                                          #
#                                                                             #
#This program is distributed in the hope that it will be useful,              #
#but WITHOUT ANY WARRANTY; without even the implied warranty of               #
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                #
#GNU Affero General Public License for more details.                          #
#                                                                             #
#You should have received a copy of the GNU Affero General Public License     #
#along with this program.  If not, see <http://www.gnu.org/licenses/>.        #
###############################################################################
from openerp import api, models
from openerp.osv import orm, fields
from lxml.html.builder import INS
from openerp.exceptions import Warning as UserError


class AccountPaymentTerm(orm.Model):
    _inherit = 'account.payment.term'
    _columns = {
        'indPag': fields.selection(
            [('0', u'Pagamento à Vista'), ('1', u'Pagamento à Prazo'),
            ('2', 'Outros')], 'Indicador de Pagamento'),
        'tPag': fields.selection(
            [('01', u'Dinheiro'),
             ('02', u'Cheque'),
             ('03', u'Cartão de Crédito'),
             ('04',u'Cartão de Débito'),
             ('05', u'Crédito Loja'),
             ('10', u'Vale Alimentação'),
             ('11', u'Vale Refeição'),
             ('12', u'Vale Presente'),
             ('13', u'Vale Combustivel'),
             ('15', u'Boleto Bancário'),
             ('90', u'Sem Pagamento'),
             ('99', u'Outros')], 'Meio de Pagamento'),
    }
    _defaults = {
        'indPag': '1',
        'tPag': '99',
    }


class AccountTax(models.Model):
    """Implement computation method in taxes"""
    _inherit = 'account.tax'

    def _compute_tax(self, cr, uid, taxes, total_line, product, product_qty,
                     precision):
        result = {'tax_discount': 0.0, 'taxes': []}

        for tax in taxes:
            if tax.get('type') == 'weight' and product:
                product_read = self.pool.get('product.product').read(
                     cr, uid, product, ['weight_net'])
                tax['amount'] = round((product_qty * product_read.get(
                    'weight_net', 0.0)) * tax['percent'], precision)

            if tax.get('type') == 'quantity':
                tax['amount'] = round(product_qty * tax['percent'], precision)

            tax['amount'] = round(total_line * tax['percent'], precision)
            tax['amount'] = round(tax['amount'] * (1 - tax['base_reduction']), precision)

            if tax.get('tax_discount'):
                result['tax_discount'] += tax['amount']

            if tax['percent']:
                tax['total_base'] = round(total_line * (1 - tax['base_reduction']), precision)
                tax['total_base_other'] = round(total_line - tax['total_base'], precision)
            else:
                tax['total_base'] = 0.00
                tax['total_base_other'] = 0.00

        result['taxes'] = taxes
        return result

    def _compute_costs(self, cr, uid, insurance_value, freight_value, other_costs_value, context=False):
        result = []
        total_included = 0.0

        company = self.pool.get('res.users').browse(cr, uid, [uid], context=context)[0].company_id

        costs = {
            company.insurance_tax_id : insurance_value,
            company.freight_tax_id : freight_value,
            company.other_costs_tax_id : other_costs_value,
        }

        for tax in costs:
            if costs[tax]:
                result.append({
                    'domain': tax.domain,
                    'ref_tax_code_id': tax.ref_tax_code_id.id,
                    'sequence': tax.sequence,
                    'total_base': costs[tax],
                    'account_paid_id': tax.account_paid_id.id,
                    'base_sign': tax.base_sign,
                    'id': tax.id,
                    'ref_base_code_id': tax.ref_base_code_id.id,
                    'account_analytic_collected_id': tax.account_analytic_collected_id.id,
                    'tax_code_id': tax.tax_code_id.id,
                    'ref_tax_sign': tax.ref_tax_sign,
                    'type': tax.type,
                    'ref_base_sign': tax.ref_base_sign,
                    'base_code_id': tax.base_code_id.id,
                    'account_analytic_paid_id': tax.account_analytic_paid_id.id,
                    'name': tax.name,
                    'account_collected_id': tax.account_collected_id.id,
                    'amount': costs[tax],
                    'tax_sign':tax.tax_sign,
                })
                total_included += costs[tax]
        return result, total_included

    #TODO
    #Refatorar este método, para ficar mais simples e não repetir
    #o que esta sendo feito no método l10n_br_account_product
    @api.v7
    def compute_all(self, cr, uid, taxes, price_unit, quantity,
                    product=None, partner=None, force_excluded=False,
                    fiscal_position=False, insurance_value=0.0,
                    freight_value=0.0, other_costs_value=0.0,
                    consumidor=False):
        """Compute taxes

        Returns a dict of the form::

        {
            'total': Total without taxes,
            'total_included': Total with taxes,
            'total_tax_discount': Total Tax Discounts,
            'taxes': <list of taxes, objects>,
            'total_base': Total Base by tax,
        }

        :Parameters:
            - 'taxes': List with all taxes id.
            - 'price_unit': Product price unit.
            - 'quantity': Product quantity.
            - 'force_excluded': Used to say that we don't want to consider
                                the value of field price_include of tax.
                                It's used in encoding by line where you don't
                                matter if you encoded a tax with that boolean
                                to True or False.
        """
        obj_precision = self.pool.get('decimal.precision')
        precision = obj_precision.precision_get(cr, uid, 'Account')
        result = super(AccountTax, self).compute_all(
            cr, uid, taxes,
            price_unit, quantity, product, partner, force_excluded)
        totaldc = icms_value = 0.0
        ipi_value = 0.0
        
        # RAFAEL PETRELLA - CIEL IT - 07/10/2016
        # Ajuste para atender Venda p/ Consumo (Add IPI na base do ICMS)
        ipi_add_base_icms = 0.00
        
        calculed_taxes = []
        for tax in result['taxes']:
            tax_list = [tx for tx in taxes if tx.id == tax['id']]
            if tax_list:
                tax_brw = tax_list[0]
            tax['domain'] = tax_brw.domain
            tax['type'] = tax_brw.type
            tax['percent'] = tax_brw.amount
            tax['base_reduction'] = tax_brw.base_reduction
            tax['amount_mva'] = tax_brw.amount_mva
            tax['tax_discount'] = tax_brw.base_code_id.tax_discount
            tax['account_deduced_id'] = tax_brw.account_deduced_id.id
            tax['account_paid_deduced_id'] = tax_brw.account_paid_deduced_id.id
        
            # RAFAEL PETRELLA - CIEL IT - 07/10/2016
            # Ajuste para atender Venda p/ Consumo (Add IPI na base do ICMS)
            tax['include_base_amount'] = tax_brw.include_base_amount

        common_taxes = [tx for tx in result['taxes'] if tx['domain'] not in ['icms', 'icmsst', 'ipi', 'icmsinter', 'icmsfcp', 'icmsintra']]
        result_tax = self._compute_tax(cr, uid, common_taxes, result['total'],
                                       product, quantity, precision)
        totaldc += result_tax['tax_discount']
        calculed_taxes += result_tax['taxes']

        # Calcula o IPI
        specific_ipi = [tx for tx in result['taxes'] if tx['domain'] == 'ipi']
        result_ipi = self._compute_tax(cr, uid, specific_ipi, result['total'],
                                       product, quantity, precision)
        totaldc += result_ipi['tax_discount']
        calculed_taxes += result_ipi['taxes']
        for ipi in result_ipi['taxes']:
            ipi_value += ipi['amount']

            # RAFAEL PETRELLA - CIEL IT - 07/10/2016
            # Ajuste para atender Venda p/ Consumo (Add IPI na base do ICMS)
            if result_ipi['taxes'][0]['include_base_amount']:
                ipi_add_base_icms += ipi['amount']

        difa = {}
        if consumidor and consumidor == '1':
            total_base = result['total'] + insurance_value + \
                freight_value + other_costs_value + ipi_value

            specific_icms_inter = [tx for tx in result['taxes']
                                   if tx['domain'] == 'icmsinter']
            specific_icms_intra = [tx for tx in result['taxes']
                                   if tx['domain'] == 'icmsintra']
            specific_icms_fcp = [tx for tx in result['taxes']
                                 if tx['domain'] == 'icmsfcp']

            # RAFAEL PETRELLA - 01/02/2017
            # Ajuste para atender simples nacional 
            if tax_list[0].company_id.fiscal_type != '3':
                total_base = 0.00

            if specific_icms_inter and specific_icms_intra:
                result_icms_inter = self._compute_tax(
                    cr, uid, specific_icms_inter, total_base,
                    product, quantity, precision)
                result_icms_intra = self._compute_tax(
                    cr, uid, specific_icms_intra, total_base,
                    product, quantity, precision)

                # BASE UNICA
                difa['vBCUFDest'] = total_base
                # ICMS origem = [BC x ALQ INTER]
                difa['pICMSUFDest'] = specific_icms_intra[0]['percent']
                difa['pICMSInterPart'] = 0.80
                # ICMS interno Destino = [BC x ALQ intra]
                difa['pICMSInter'] = specific_icms_inter[0]['percent']
                # ICMS destino = [BC x ALQ intra] - ICMS origem
                icms_difa = ((difa['vBCUFDest'] * difa['pICMSUFDest']) -
                             (difa['vBCUFDest'] * difa['pICMSInter']))
                if specific_icms_fcp:
                    result_icms_fcp = self._compute_tax(
                        cr, uid, specific_icms_fcp, total_base,
                        product, quantity, precision)
                    # % Fundo pobreza
                    difa['pFCPUFDest'] = specific_icms_fcp[0]['percent']
                    difa['vFCPUFDest'] = difa['vBCUFDest'] * difa['pFCPUFDest']

                    result_icms_fcp['taxes'][0]['amount'] = \
                        round(difa['vFCPUFDest'], 2)
                    calculed_taxes += result_icms_fcp['taxes']

                difa['vICMSUFDest'] = icms_difa * difa['pICMSInterPart']
                difa['vICMSUFRemet'] = icms_difa * (1-difa['pICMSInterPart'])

                result_icms_inter['taxes'][0]['amount'] = \
                    round(difa['vICMSUFRemet'], 2)
                result_icms_intra['taxes'][0]['amount'] = \
                    round(difa['vICMSUFDest'], 2)

                calculed_taxes += result_icms_inter['taxes']
                calculed_taxes += result_icms_intra['taxes']

        else:
            total_base = result['total'] + insurance_value + \
            freight_value + other_costs_value

        # Calcula ICMS
        specific_icms = [tx for tx in result['taxes'] if tx['domain'] == 'icms']

        # RAFAEL PETRELLA - CIEL IT - 07/10/2016
        # Ajuste para atender Venda p/ Consumo (Add IPI na base do ICMS)
        result_icms = self._compute_tax(cr, uid,
            specific_icms, total_base+ipi_add_base_icms, product, quantity, precision)
        totaldc += result_icms['tax_discount']
        calculed_taxes += result_icms['taxes']
        if result_icms['taxes']:
            icms_value = result_icms['taxes'][0]['amount']

        # Calcula ICMS ST
        specific_icmsst = [tx for tx in result['taxes'] if tx['domain'] == 'icmsst']
        result_icmsst = self._compute_tax(cr, uid, specific_icmsst, result['total'], product, quantity, precision)
        totaldc += result_icmsst['tax_discount']
        if result_icmsst['taxes']:
            icms_st_percent = result_icmsst['taxes'][0]['percent']
            icms_st_percent_reduction = result_icmsst['taxes'][0]['base_reduction']
            icms_st_base = round((((result['total'] + ipi_value) * (1 - icms_st_percent_reduction)) * (1 + result_icmsst['taxes'][0]['amount_mva'])), precision)
            icms_st_base_other = round(((result['total'] + ipi_value) * (1 + result_icmsst['taxes'][0]['amount_mva'])), precision) - icms_st_base
            result_icmsst['taxes'][0]['total_base'] = icms_st_base
            result_icmsst['taxes'][0]['amount'] = round((icms_st_base  * icms_st_percent) - icms_value, precision)
            result_icmsst['taxes'][0]['icms_st_percent'] = icms_st_percent
            result_icmsst['taxes'][0]['icms_st_percent_reduction'] = icms_st_percent_reduction
            result_icmsst['taxes'][0]['icms_st_base_other'] = icms_st_base_other

            calculed_taxes += result_icmsst['taxes']

        costs, costs_values = self._compute_costs(cr, uid, insurance_value, freight_value, other_costs_value)
        calculed_taxes += costs
        result['total_included'] += costs_values

        return {
            'total': result['total'],
            'total_included': result['total_included'],
            'total_tax_discount': totaldc,
            'taxes': calculed_taxes
        }

    @api.v8
    def compute_all(self, price_unit, quantity,
                    product=None, partner=None, force_excluded=False,
                    fiscal_position=False, insurance_value=0.0,
                    freight_value=0.0, other_costs_value=0.0, consumidor=False):
        return self._model.compute_all(
            self._cr, self._uid, self, price_unit, quantity,
            product=product, partner=partner, force_excluded=force_excluded,
            fiscal_position=fiscal_position, insurance_value=insurance_value,
            freight_value=freight_value, other_costs_value=other_costs_value,
            consumidor=consumidor)
