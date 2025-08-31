export function createPageUrl(pageName) {
  // Simple URL creation, can be expanded for more complex routing
  switch (pageName) {
    case 'Messenger':
      return '/';
    case 'Archived':
      return '/archived';
    default:
      return `/${pageName.toLowerCase()}`;
  }
}