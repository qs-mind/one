import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { setLanguage, texts } from '../../i18n';
import { fakeSources } from '../../project/fake';
import { thread } from '../../deliverables/fixtures';
import { workspaceApi } from '../api';
import { FilePages, type FilePage } from './FileDoc';
import type { FileRegion } from '../../deliverables/types';

beforeEach(() => setLanguage('en'));
const state: FilePage = {pages: 2, page: 1, setPage: vi.fn(), mode: 'image', setMode: vi.fn(), pageOf: 'Page 1 of 2'};
const region: FileRegion = {kind: 'file_region', file_id: 'f1', page: 1, box: [60, 80, 180, 160]};

it('prefers a stored source box and otherwise requests the cited value', async () => {
  const sources = fakeSources({pages: {f1: 2}});
  sources.pageBoxes = vi.fn().mockResolvedValue({width: 600, height: 800, boxes: [[10, 20, 40, 50]]});
  const {rerender, container} = render(<FilePages sources={sources} fileId="f1" state={state} width={600} opened={{key:'file:f1', anchor:{page:1, box:region.box, value:'3450'}}} />);
  await waitFor(() => expect(container.querySelector('rect')).toHaveAttribute('x', '60'));
  expect(sources.pageBoxes).toHaveBeenLastCalledWith('f1', 1, undefined);
  rerender(<FilePages sources={sources} fileId="f1" state={state} width={1400} opened={{key:'file:f1', anchor:{page:1, value:'3450'}}} />);
  await waitFor(() => expect(container.querySelector('rect')).toHaveAttribute('x', '10'));
  expect(sources.pageBoxes).toHaveBeenLastCalledWith('f1', 1, '3450');
});

it('creates a region thread and reopens its page from the shared comment list', async () => {
  const user = userEvent.setup();
  const sources = fakeSources({pages: {f1: 2}});
  const made = thread('region1', {deliverable_id:null, body:'Sample comment', anchor:region, anchor_now:region});
  sources.pageBoxes = vi.fn().mockResolvedValue({width:600, height:800, boxes:[]});
  sources.fileComments = vi.fn().mockResolvedValueOnce([]).mockResolvedValue([made]);
  sources.addFileComment = vi.fn().mockResolvedValue(made);
  render(<FilePages projectId="p1" sources={sources} fileId="f1" state={state} width={600} />);
  await user.click(await screen.findByRole('button', {name:texts.regionSelect.en}));
  const overlay = screen.getByTestId('pdf-regions');
  vi.spyOn(overlay,'getBoundingClientRect').mockReturnValue({left:0, top:0, width:600, height:800} as DOMRect);
  fireEvent.pointerDown(overlay, {clientX:60, clientY:80, button:0, pointerId:1});
  fireEvent.pointerUp(overlay, {clientX:180, clientY:160, pointerId:1});
  await user.type(screen.getByRole('textbox', {name:texts.reviewCommentText.en}), 'Sample comment');
  await user.click(screen.getByRole('button', {name:texts.reviewAddComment.en}));
  expect(sources.addFileComment).toHaveBeenCalledWith('f1', region, 'Sample comment');
  await screen.findByText('Sample comment');
  const open = vi.spyOn(workspaceApi, 'open');
  await user.click(screen.getByRole('button', {name:/Page 1/i}));
  expect(open).toHaveBeenCalledWith('file:f1', {page:1, box:region.box});
});

it('does not reuse a source box on another page', async () => {
  const sources = fakeSources({pages: {f1:2}});
  sources.pageBoxes = vi.fn().mockResolvedValue({width:600, height:800, boxes:[]});
  const {container} = render(<FilePages sources={sources} fileId="f1" state={{...state,page:2}} width={600} opened={{key:'file:f1',anchor:{page:1,box:region.box}}} />);
  await screen.findByRole('img');
  expect(container.querySelector('rect')).toBeNull();
});

it('shows every open region on its page before a thread is clicked', async () => {
  const sources = fakeSources({pages: {f1: 2}});
  const other: FileRegion = {...region, page: 2, box: [200, 300, 250, 350]};
  const second: FileRegion = {...region, box: [300, 80, 350, 160]};
  sources.pageBoxes = vi.fn().mockResolvedValue({width:600, height:800, boxes:[]});
  sources.fileComments = vi.fn().mockResolvedValue([
    thread('open1', {anchor:region, anchor_now:region}),
    thread('open2', {anchor:second, anchor_now:second}),
    thread('other-page', {anchor:other, anchor_now:other}),
    thread('closed', {anchor:region, anchor_now:region, status:'closed'}),
  ]);
  const {container, rerender} = render(<FilePages projectId="p1" sources={sources} fileId="f1" state={state} width={600} />);
  await waitFor(() => expect([...container.querySelectorAll('rect')].map(rect => rect.getAttribute('x'))).toEqual(['60', '300']));
  rerender(<FilePages projectId="p1" sources={sources} fileId="f1" state={{...state, page:2}} width={600} />);
  await waitFor(() => expect([...container.querySelectorAll('rect')].map(rect => rect.getAttribute('x'))).toEqual(['200']));
});
