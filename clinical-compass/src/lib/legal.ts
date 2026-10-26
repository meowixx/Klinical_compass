export const legalDetails = {
  operator: process.env.NEXT_PUBLIC_OPERATOR_NAME?.trim() || 'Владелец сервиса «Клинический компас»',
  address: process.env.NEXT_PUBLIC_OPERATOR_ADDRESS?.trim() || 'Не указан',
  email: process.env.NEXT_PUBLIC_PRIVACY_EMAIL?.trim() || 'Не указан',
  registry: process.env.NEXT_PUBLIC_OPERATOR_REGISTRY?.trim() || '',
};

export const legalDetailsComplete = legalDetails.address !== 'Не указан' && legalDetails.email !== 'Не указан';

