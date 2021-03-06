# © 2015 Esther Martín - AvanzOSC
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, models, fields, exceptions, _


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mrp_production_id = fields.Many2one(
        comodel_name='mrp.production', string='Production', copy=False)
    product_line_ids = fields.One2many(
        comodel_name='mrp.production.product.line',
        inverse_name='sale_line_id', string='Product line')
    manufacturable_product = fields.Boolean(
        compute="compute_manufacturable_product")

    @api.depends("product_id.route_ids")
    def compute_manufacturable_product(self):
        manufacture = self.env.ref('mrp.route_warehouse0_manufacture')
        for line in self:
            line.manufacturable_product = (manufacture in
                                           line.product_id.route_ids)

    def _action_mrp_dict(self):
        values = {
            'product_id': self.product_id.id or False,
            'product_qty': self.product_uom_qty,
            'product_uom_id': self.product_uom.id,
            'sale_line_id': self.id,
            # 'product_attribute_ids': [(0, 0, x) for x in attribute_list],
            'active': False,
        }
        return values

    @api.multi
    def _action_launch_stock_rule(self):
        for line in self:
            if not line.mrp_production_id:
                super(SaleOrderLine, line.with_context(sale_line_fields={
                    'sale_line_id': line.id,
                    'active': True,
                }))._action_launch_stock_rule()
                created_mo = self.env['mrp.production'].search(
                    [('sale_line_id', '=', line.id)])
                if created_mo:
                    try:
                        line.mrp_production_id = created_mo.id
                        created_mo.with_context(sale_line_id=line.id
                                                ).action_compute()
                    except ValueError:
                        raise exceptions.UserError(_("Multiple "
                                                     "manufacture orders for "
                                                     "same order line"))
        return True

    @api.multi
    def action_create_mrp(self):
        if self.product_uom_qty <= 0:
            raise exceptions.Warning(_('The quantity must be positive.'))
        values = self._action_mrp_dict()
        mrp = self.env['mrp.production'].create(values)
        mrp.with_context(sale_line_id=self.id).action_compute()
        self.mrp_production_id = mrp


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def action_create_mrp_from_lines(self):
        for sale in self:
            for line in sale.order_line.filtered(
                    lambda x: not x.mrp_production_id and
                    x.manufacturable_product):
                try:
                    line.action_create_mrp()
                except exceptions.MissingError:
                    continue

    @api.multi
    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for mrp in self.mapped('order_line.mrp_production_id'):
            mrp.write({
                'active': True,
            })
        return res

    @api.multi
    def action_show_manufacturing_orders(self):
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
            'search_view_id': self.env.ref(
                'mrp.view_mrp_production_filter').id,
            'domain': "[('sale_order_id', '=', " + str(self.id) + "),\
                        '|', ('active', '=', True), ('active', '=', False)]",
            'context': self.env.context
        }

    @api.multi
    def action_show_scheduled_products(self):
        return {
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'mrp.production.product.line',
            'type': 'ir.actions.act_window',
            'search_view_id': self.env.ref(
                'mrp_scheduled_products.mrp_production_product_search_view'
            ).id,
            'domain': "[('sale_line_id', 'in', " + str(self.order_line.ids) +
                      ")]",
            'context': self.env.context
        }
