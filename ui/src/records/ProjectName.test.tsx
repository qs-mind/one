import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ProjectName } from './ProjectName';
import { currentProject, setCurrentProject } from './project';
import { setLanguage, texts } from '../i18n';

vi.mock('../activity', () => ({ subscribeActivity: () => () => {} }));

afterEach(() => { vi.unstubAllGlobals(); setCurrentProject(undefined); });
it('shows the file and page and saves a name edited in place', async () => {
  setLanguage('en');
  const project = { id: 'sample', name: 'Sample hospital', created_at: '', name_source: { file_id: 'f', file: 'sample.pdf', locator: { page: 2 } } };
  setCurrentProject(project);
  const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => Response.json({ ...project, name: 'My sample', name_source: null }));
  vi.stubGlobal('fetch', fetch);
  render(<ProjectName project={project} />);
  expect(screen.getByText(/sample.pdf/)).toHaveTextContent('sample.pdf · Page 2');
  fireEvent.click(screen.getByRole('button', { name: 'Sample hospital' }));
  fireEvent.change(screen.getByRole('textbox', { name: texts.projectName.en }), { target: { value: 'My sample' } });
  fireEvent.blur(screen.getByRole('textbox'));
  await waitFor(() => expect(currentProject()?.name).toBe('My sample'));
  expect(fetch.mock.calls[0]?.[1]).toMatchObject({ method: 'PATCH', body: JSON.stringify({ name: 'My sample' }) });
});

it('saves while typing without leaving the field', async () => {
  setLanguage('en');
  const project = { id: 'sample', name: 'Sample hospital', created_at: '' };
  setCurrentProject(project);
  const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => Response.json({ ...project, name: 'Typed sample' }));
  vi.stubGlobal('fetch', fetch);
  render(<ProjectName project={project} />);
  fireEvent.click(screen.getByRole('button', { name: project.name }));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Typed sample' } });
  await waitFor(() => expect(currentProject()?.name).toBe('Typed sample'));
  expect(screen.getByRole('textbox')).toBeInTheDocument();
});
