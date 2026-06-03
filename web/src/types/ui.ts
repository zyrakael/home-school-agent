export type StatusTone = 'pending' | 'submitted' | 'late' | 'missing'

export const statusLabelMap: Record<string, string> = {
  pending: '待提交',
  submitted: '已提交',
  late: '晚提交',
  missing: '未提交',
}
